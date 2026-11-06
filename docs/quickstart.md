# Connect an existing knowledge base

A versioned Microsoft Foundry prompt agent connected to an existing Azure AI Search Knowledge Base through MCP, with a guarded terminal client. The application deploys the **agent definition**. An optional [dedicated demo lab](../README.md#run-the-dedicated-demo-lab) provisions isolated Azure resources and synthetic documents; no HTTP API is served.

[Complete documentation](../README.md) · [Offline CI setup](../GITHUB_ACTIONS.md)

## Prerequisites

Use Python **3.12**, an existing Foundry project and deployed Responses/MCP-compatible model, a populated Search Knowledge Base, and a RemoteTool project connection pointing at its MCP endpoint.

For managed-identity connection authentication, configure the Search audience and grant the actual connection identity **Search Index Data Reader** on Search. The deployment identity needs permissions to manage agents and invoke the model, for example **Foundry User** (formerly Azure AI User) at the appropriate Foundry scope according to your organization's RBAC policy. Validate both client-to-Foundry and Foundry-to-Search network access.

The client uses the connection's shared KB access. It does not implement per-user document ACL enforcement or token passthrough. Only use a KB that all intended users are authorized to read.

## Install and configure

```bash
python -m venv .venv
source .venv/bin/activate
# Windows Git Bash: source .venv/Scripts/activate
# Windows PowerShell: .venv\Scripts\Activate.ps1
python -m pip install --require-hashes -r requirements.txt
python -m pip check
cp .env.example .env
az login
```

Fill in the project endpoint, KB MCP endpoint and RemoteTool connection name. Model deployment and agent name default to `gpt-4.1-mini` and `RagAgent`. Process environment variables override the local `.env`.

Set `AZURE_CREDENTIAL_MODE=cli` for explicit Azure CLI authentication, `managed_identity` for an Azure runtime, or `default` for the noninteractive Entra credential chain. For a user-assigned runtime identity, set `MANAGED_IDENTITY_CLIENT_ID`. In CLI mode, optionally set `AZURE_CLI_SUBSCRIPTION` to scope token requests without changing the global `az` default.

The example MCP endpoint uses preview API `2026-08-01-preview`. The lab uses GA `2026-04-01` for index/source provisioning and preview `2026-08-01-preview` for the knowledge base, explicitly set to `minimal` reasoning and `extractiveData` without a KB model. Use your actual Azure-provided endpoint if it requires another version. Assess preview features separately before production use. The grounding parser accepts nonempty `content` records with `ref_id`, directly or wrapped in MCP `content[].text` or `result.content[].text`. Unknown schemas are rejected.

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

Replace these sample questions and expected substring with tests for your KB. The known-answer check requires actual retrieval, valid citations and the expected substring. The unknown-answer check requires exact English `I don't know`, even for Polish questions; all agent responses are configured to be in English, regardless of the question language. Retrieval or validation failures exit with code 1.

Deployment reuses the latest version when its stored `config_sha256` and `managed_by` metadata match the requested definition’s fingerprint. Server-added defaults do not affect reuse; versions without matching metadata create a new candidate. A changed definition, or `--force`, creates a new immutable version. An atomic manifest records the candidate version. Treat it as a verified release only after live checks pass.

Pin the tested `AGENT_VERSION` in the client environment:

```bash
python chat.py
python chat.py --version 2 --question "What is the return period?" --json
```

Version precedence is `--version`, then `AGENT_VERSION`, then a manifest matching the project endpoint and agent name. Clients never automatically select `latest`.

## Grounding and errors

The pinned agent definition forces the KB retrieval tool. Requests inherit that setting and deliberately omit `tool_choice` to avoid conflicting overrides. Exactly one retrieval call per response is accepted; a second call fails with `multiple_retrieval_calls`. Before displaying a factual answer, the client checks response completion, successful MCP retrieval, nonempty evidence and citation IDs matching the current retrieval results. It accepts `[ref_id:X]` identifiers or native `url_citation` annotations with valid
text offsets and a unique, exact URL match in the current retrieval results. It
displays source metadata and does not invent or fetch source URLs.

These are provenance checks, **not proof that every claim follows from the cited evidence**. Evaluate answer accuracy and retrieval quality using representative data. Other clients calling the Foundry agent directly bypass this repository's response checks.

Interactive validation failures display an unavailable-answer message and a safe diagnostic on stderr, distinct from a valid refusal. One-shot requests fail with code 1 and never emit rejected answers. Network and permission failures are distinguished from legitimate unknown answers. Remote error bodies and document chunks are not printed in diagnostics.

Only accepted answers enter bounded local history. Each turn performs fresh retrieval. Requests use `store=False` without persistent Conversations; configure Azure service retention separately. Responses SDK retries are capped at two. Agent management has no automatic retries to avoid duplicate versions after a lost create response; inspect Azure state before retrying a timed-out deployment.

## Rollback and cleanup

Point clients at a previous verified version or restore its release manifest. Creating a candidate changes Foundry's `latest` before smoke checks, so all production clients must use an explicit version.

```bash
python delete_rag_agent.py --version 2 --yes
python delete_rag_agent.py --all --yes
```

There is no implicit deletion target. Move clients away from a version before deleting it; deletion does not update existing manifests or client configuration.

## Offline CI and local deployment

Pushes and PRs to `main` run only lint, formatting, offline tests and dependency checks. GitHub Actions does not authenticate to Azure or deploy agents, including on manual workflow dispatch. It has no OIDC permission, Azure secrets or deployment job. See [GITHUB_ACTIONS.md](../GITHUB_ACTIONS.md).

Deploy and run live smoke checks on your own machine using the commands above after `az login`. Retain the verified local manifest and pin its agent version in client environments.

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


## MCP response formats

The client accepts the documented `ref_id`/`content` records and the live MCP
`{"documents": [{"id": "...", "content": "..."}]}` envelope. For the latter,
citations use the exact outer document ID as `[ref_id:<id>]`, not its array
position or an ID embedded inside JSON document content. String-encoded JSON
and MCP text wrappers are decoded with bounded recursion. Unknown or malformed
formats remain errors. Returned URLs are preserved as metadata and never fetched
by the validator. This validates provenance, not semantic support of every claim.


