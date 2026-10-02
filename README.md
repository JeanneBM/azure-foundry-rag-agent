# Azure Foundry RAG Agent

A RAG agent on Microsoft Foundry Agent Service that uses an Azure AI Search Knowledge Base through MCP. This repository deploys an **agent version** and provides a terminal client. The knowledge base, indexes, model and RemoteTool connection must be prepared beforehand.

The client forces a `knowledge_base_retrieve` call and validates the result before displaying the answer. Factual answers must cite identifiers actually returned by the current retrieval. These checks establish source provenance, but do not prove that every sentence follows from the documents. Retrieval quality and answer faithfulness require evaluation on your target data.

[Quick-start guide](README_EN.md) · [Offline GitHub Actions](GITHUB_ACTIONS.md)

## Requirements and scope

- Python **3.12**: the dependency locks and CI target this version.
- A Foundry project with a deployed model supporting the Responses API and MCP.
- Azure AI Search with a ready Knowledge Base and completed indexing.
- A Foundry RemoteTool connection pointing to the exact MCP endpoint.
- Azure CLI for local authentication, or Managed Identity in an Azure runtime.

This is a managed Foundry agent deployment and a CLI client. The repository does not provision infrastructure, index documents or expose a public HTTP API. Response validation is implemented by this repository's client; calling the agent through another client bypasses these checks.

## Prepare Azure

1. Prepare a Knowledge Base containing the content your users should be able to access. In the portal, verify that retrieval returns chunks and `ref_id` identifiers.
2. Deploy your chosen model in the Foundry project. `MODEL_DEPLOYMENT` is the **deployment name**, not the model's catalog name.
3. Create a RemoteTool connection to the Knowledge Base endpoint. For Managed Identity authentication, set the audience to `https://search.azure.com/` and grant the identity used by the connection the **Search Index Data Reader** role on the Search service. Verify the actual identity in the connection settings.
4. Grant the deployment identity permissions to manage project agents and invoke the model, for example **Foundry User** (formerly Azure AI User) on the appropriate Foundry resource, according to your organization's RBAC policy. Limit the scope to the required resource.
5. Ensure network connectivity for both client → Foundry and Foundry → Search. For private endpoints, use an appropriately connected runtime.

All users of this client share the KB connection's permissions. There is no user identity passthrough or separate document ACL enforcement. The knowledge base and its connection must be intended for a shared, authorized audience.

## Installation

```bash
git clone https://github.com/JeanneBM/jb-foundry-rag-agent.git
cd jb-foundry-rag-agent
python -m venv .venv
source .venv/bin/activate
# Windows PowerShell: .venv\Scripts\Activate.ps1
python -m pip install --require-hashes -r requirements.txt
python -m pip check
cp .env.example .env
az login
```

Fill in `.env` with your actual values. Do not include tokens or keys in endpoint URLs. Existing process environment variables take precedence over `.env`.

| Variable | Purpose |
|---|---|
| `PROJECT_ENDPOINT` | HTTPS project endpoint ending in `/api/projects/<project>` |
| `RAG_MCP_ENDPOINT` | Exact KB endpoint: `/knowledgebases/<kb>/mcp?api-version=...` |
| `PROJECT_CONNECTION_NAME` | Name of the existing RemoteTool connection |
| `MODEL_DEPLOYMENT` | Model deployment name; defaults to `gpt-4.1-mini` |
| `AGENT_NAME` | Agent name; defaults to `RagAgent` |
| `AGENT_VERSION` | Explicit tested version for the client; reads the manifest when unset |
| `DEPLOYMENT_FILE` | Release manifest; defaults to `deployment.json` |
| `AZURE_CREDENTIAL_MODE` | `default`, `cli` or `managed_identity` |
| `MANAGED_IDENTITY_CLIENT_ID` | Optional client ID of a user-assigned identity |
| `REQUEST_TIMEOUT_SECONDS` | Timeout for a single request attempt; defaults to 120 seconds |
| `MAX_OUTPUT_TOKENS` | Generated response limit; defaults to 2048 |
| `MAX_QUESTION_CHARS` | Question length limit; defaults to 8000 characters |
| `HISTORY_TURNS` | Retained question/answer pairs; defaults to 6; 0 disables history |

The example uses GA Search API `2026-04-01`, which returns extractive data. If your KB configuration requires another version, use the endpoint provided by Azure. Assess preview features separately before production deployment. The parser accepts grounding records with `ref_id` and nonempty `content`, directly or wrapped in MCP `content[].text` / `result.content[].text`. Other formats are rejected.

## Create a version and verify the deployment

```bash
python create_rag_agent.py
```

The script compares the complete definition with the latest version. If they match, it reuses the existing version. A changed definition creates a new immutable version. `--force` creates a new version even without changes. The result is written atomically to `deployment.json`.

**The newly created manifest describes a candidate** until it passes checks on Azure. Use two questions tailored to your knowledge base: one with a known answer and one the KB cannot answer.

```bash
python smoke_test.py \
  --known-question "What is the product return period?" \
  --expected-substring "30 days" \
  --unknown-question "What is the private phone number of a person not mentioned in the documents?"
```

These questions are examples. The test requires successful retrieval, citations and the expected substring for the first question, and exact `I don't know` for the second. An error exits with code 1; it is not treated as a successful unknown-answer check.

After the checks pass, set `AGENT_VERSION` to the version number from the manifest in the client environment. The client never automatically selects `latest`. Precedence: `--version` → `AGENT_VERSION` → a manifest matching the agent name and project endpoint.

```bash
python chat.py
python chat.py --version 2 --question "What is the return period?" --json
```

The client displays `[ref_id:X]` citations and metadata for the cited sources. It does not invent URLs. If a record has no URL, the client will not display one.

## Error handling

- Missing retrieval, MCP errors, incomplete responses or citations outside the current results cause the model's answer to be rejected.
- Interactive mode displays `I don't know` and a separate diagnostic on stderr. `--question` mode exits with code 1 without emitting an unverified answer.
- Network and RBAC errors are distinguished from a lack of knowledge. Remote error bodies, tokens and document chunks are not printed in diagnostics.
- Only accepted answers enter local history. Every new question requires fresh retrieval.
- The Responses API is called with `store=False`; the client does not create persistent Conversations. Configure Azure service retention and monitoring policies separately.
- Responses calls have at most two SDK retries. The timeout applies to each attempt. Agent management has no automatic retries to avoid duplicate versions after a lost response. After a timeout during creation, inspect the agent's state in Azure first.

## Rollback and deletion

Roll back the client by setting a previous verified `AGENT_VERSION` or passing `--version`. This does not delete any versions in Azure. Retain the previous release manifest.

Creating a new version changes `latest` in Foundry even before the smoke test. All production clients should use explicitly pinned versions; an agent name without a version does not isolate them from the candidate.

```bash
python delete_rag_agent.py --version 2 --yes
# Delete the agent and ALL of its versions:
python delete_rag_agent.py --all --yes
```

There is no default version to delete. Deletion does not update manifests or client configuration — first move clients to a version you will retain.

## Offline CI and local deployment

Pushes and PRs to `main` run only lint, formatting, offline tests and dependency checks. GitHub Actions has no Azure login, OIDC permission, Azure secrets or deployment job. A manual workflow dispatch runs the same offline checks. See [GITHUB_ACTIONS.md](GITHUB_ACTIONS.md).

Deploy and verify from your own machine using `az login`, `python create_rag_agent.py` and `python smoke_test.py`. Keep the verified `deployment.json` locally and pin its version in your client configuration.

```bash
python -m pip install --require-hashes -r requirements-dev.txt
ruff check .
ruff format --check .
python -m pytest -q
```

Offline tests use actual SDK models/serialization and mock HTTP transports. They cannot confirm RBAC, networking or KB content — `smoke_test.py` checks the live environment.

Runtime and development dependencies are separate and locked with hashes. After deliberately changing versions in the `.in` files, regenerate the locks on Python 3.12 and rerun the checks:

```bash
python -m pip install pip-tools==7.6.1
pip-compile --generate-hashes --no-emit-index-url --no-emit-trusted-host -o requirements.txt requirements.in
pip-compile --generate-hashes --no-emit-index-url --no-emit-trusted-host -o requirements-dev.txt requirements-dev.in
```

## Service documentation

- [Connect Foundry to a Knowledge Base](https://learn.microsoft.com/en-us/azure/foundry/agents/how-to/foundry-iq-connect)
- [MCP format and Search API versions](https://learn.microsoft.com/en-us/azure/search/agentic-retrieval-how-to-retrieve)
- [AgentReference and the Responses API](https://learn.microsoft.com/en-us/rest/api/microsoft-foundry/aiproject)
- [Runtime and response storage](https://learn.microsoft.com/en-us/azure/foundry/agents/concepts/runtime-components)

## License

MIT
