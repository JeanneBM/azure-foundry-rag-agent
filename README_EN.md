# Azure Foundry RAG Agent

A versioned Microsoft Foundry prompt agent connected to an existing Azure AI Search Knowledge Base through MCP, with a guarded terminal client. This repository deploys the **agent definition**; it does not provision Azure infrastructure, ingest documents, or serve an HTTP API.

[Complete documentation](README.md) · [CI/CD and OIDC setup](GITHUB_ACTIONS.md)

## Prerequisites

Use Python **3.12**, an existing Foundry project and deployed Responses/MCP-compatible model, a populated Search Knowledge Base, and a RemoteTool project connection pointing at its MCP endpoint.

For managed-identity connection authentication, configure the Search audience and grant the actual connection identity **Search Index Data Reader** on Search. The deployment identity needs permissions to manage agents and invoke the model, for example **Foundry User** (formerly Azure AI User) at the appropriate Foundry scope according to your organization's RBAC policy. Validate both client-to-Foundry and Foundry-to-Search network access.

The client uses the connection's shared KB access. It does not implement per-user document ACL enforcement or token passthrough. Only use a KB that all intended users are authorized to read.

## Install and configure

```bash
python -m venv .venv
source .venv/bin/activate
# Windows PowerShell: .venv\Scripts\Activate.ps1
python -m pip install --require-hashes -r requirements.txt
python -m pip check
cp .env.example .env
az login
```

Fill in the project endpoint, KB MCP endpoint and RemoteTool connection name. Model deployment and agent name default to `gpt-4.1-mini` and `RagAgent`. Process environment variables override the local `.env`.

Set `AZURE_CREDENTIAL_MODE=cli` for explicit Azure CLI authentication, `managed_identity` for an Azure runtime, or `default` for the noninteractive Entra credential chain. For a user-assigned runtime identity, set `MANAGED_IDENTITY_CLIENT_ID`.

The example Search endpoint uses GA API `2026-04-01` for extractive retrieval. Use your actual Azure-provided endpoint if it requires another version. Assess preview features separately before production use. The grounding parser accepts nonempty `content` records with `ref_id`, directly or wrapped in MCP `content[].text` or `result.content[].text`. Unknown schemas are rejected.

| Setting | Default / purpose |
|---|---|
| `AGENT_VERSION` | Explicit tested version; otherwise use the release manifest |
| `DEPLOYMENT_FILE` | `deployment.json` |
| `REQUEST_TIMEOUT_SECONDS` | 120 seconds per request attempt |
| `MAX_OUTPUT_TOKENS` | 2048 |
| `MAX_QUESTION_CHARS` | 8000 |
| `HISTORY_TURNS` | 6 accepted turns; 0 disables history |

## Deploy and verify

```bash
python create_rag_agent.py
python smoke_test.py \
  --known-question "What is the documented return period?" \
  --expected-substring "30 days" \
  --unknown-question "What is a private phone number absent from the documents?"
```

Replace these sample questions and expected substring with tests for your KB. The known-answer check requires actual retrieval, valid citations and the expected substring. The unknown-answer check requires exact `I don't know`. Retrieval or validation failures exit with code 1.

Deployment reuses the latest version when its complete definition matches. A changed definition, or `--force`, creates a new immutable version. An atomic manifest records the candidate version. Treat it as a verified release only after live checks pass.

Pin the tested `AGENT_VERSION` in the client environment:

```bash
python chat.py
python chat.py --version 2 --question "What is the return period?" --json
```

Version precedence is `--version`, then `AGENT_VERSION`, then a manifest matching the project endpoint and agent name. Clients never automatically select `latest`.

## Grounding and errors

Both the agent definition and each request force the KB retrieval tool. Before displaying a factual answer, the client checks response completion, successful MCP retrieval, nonempty evidence and citation IDs matching the current retrieval results. It displays `[ref_id:X]` citations and source metadata; it does not invent source URLs.

These are provenance checks, **not proof that every claim follows from the cited evidence**. Evaluate answer accuracy and retrieval quality using representative data. Other clients calling the Foundry agent directly bypass this repository's response checks.

Interactive validation failures display `I don't know` and a separate safe diagnostic on stderr. One-shot requests fail with code 1 and never emit rejected answers. Network and permission failures are distinguished from legitimate unknown answers. Remote error bodies and document chunks are not printed in diagnostics.

Only accepted answers enter bounded local history. Each turn performs fresh retrieval. Requests use `store=False` without persistent Conversations; configure Azure service retention separately. Responses SDK retries are capped at two. Agent management has no automatic retries to avoid duplicate versions after a lost create response; inspect Azure state before retrying a timed-out deployment.

## Rollback and cleanup

Point clients at a previous verified version or restore its release manifest. Creating a candidate changes Foundry's `latest` before smoke checks, so all production clients must use an explicit version.

```bash
python delete_rag_agent.py --version 2 --yes
python delete_rag_agent.py --all --yes
```

There is no implicit deletion target. Move clients away from a version before deleting it; deletion does not update existing manifests or client configuration.

## CI/CD and development

Pushes and PRs to `main` run lint, formatting, offline tests and dependency checks. A manual workflow dispatch on `main` with `deploy=true` creates or reuses a candidate using OIDC, runs live KB smoke checks, then uploads the verified release manifest. See [GITHUB_ACTIONS.md](GITHUB_ACTIONS.md).

```bash
python -m pip install --require-hashes -r requirements-dev.txt
ruff check .
ruff format --check .
python -m pytest -q
```

Offline tests exercise actual SDK models and HTTP serialization, but cannot validate live RBAC, networking or KB content. Regenerate hashed runtime and development locks on Python 3.12 with `pip-tools==7.6.1` after changing the `.in` files, then rerun checks. Runtime dependencies exclude test and lint tools.

## Service references

- [Foundry KB connection](https://learn.microsoft.com/en-us/azure/foundry/agents/how-to/foundry-iq-connect)
- [Search MCP output and API versions](https://learn.microsoft.com/en-us/azure/search/agentic-retrieval-how-to-retrieve)
- [Foundry Responses API](https://learn.microsoft.com/en-us/rest/api/microsoft-foundry/aiproject)

## License

MIT
