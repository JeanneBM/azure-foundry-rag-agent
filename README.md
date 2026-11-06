# Azure Foundry RAG Agent

A Python application for answering questions from an Azure AI Search knowledge base
through a versioned Microsoft Foundry agent and MCP. It includes a guarded terminal
client, a disposable Azure demo lab and automated offline tests.

The included **RagDemo** assistant covers **product returns and support hours**.
Answers are configured to be in English, cite retrieved sources and refuse questions
outside the connected documents. This is a document Q&A demo, not a general assistant.

[Use your own knowledge base](docs/quickstart.md) · [Lab reports](docs/lab-validation.md)
· [Troubleshooting](docs/troubleshooting.md) · [GitHub Actions](GITHUB_ACTIONS.md)

## Demo knowledge base

The lab indexes two synthetic documents from [examples/lab-documents.json](examples/lab-documents.json).

| Document | Information available |
| --- | --- |
| Demo return policy | Products can be returned within **30 days after delivery**. |
| Demo support hours | Support is open **Monday–Friday, 09:00–17:00 UTC**. No personal contact details are included. |

Try `What is the product return period?`, `What are the support hours?` and
`What is Kubernetes?`. The last question is outside the demo corpus and should
produce exactly `I don't know`. A validation error is a failed request, not a refusal.
The interactive terminal displays an introduction with the demo's scope.

## How it works

1. The pinned Foundry agent calls `knowledge_base_retrieve` on the connected Search KB.
2. The KB returns matching document content. The demo uses text search with semantic
   ranking, `minimal` reasoning and `extractiveData`; it has no retrieval LLM,
   embedding deployment, vector fields or custom chunking pipeline.
3. The Foundry model generates the answer. Its instructions restrict responses to
   evidence in the documents and require source citations.
4. Before displaying the answer, the Python client verifies retrieval completion and
   citation provenance. Only accepted turns enter the bounded local chat history.

The agent definition forces the retrieval tool; response requests inherit that setting.
The client requires exactly one retrieval call per answer because reference IDs are
scoped to a call. It supports `ref_id` records and the observed `documents`/`id`
envelope, including JSON-encoded MCP text wrappers.

Citations can use `[ref_id:X]` with an actual returned ID or native `url_citation`
annotations. A native URL must match exactly one document from the same retrieval,
with valid text offsets. Unknown IDs, invented URLs, ambiguous matches, malformed
results and uncited factual answers are rejected. Citation URLs are never fetched
by the validator.

**These checks establish provenance, not whether every claim follows from its source.**
The language and topic rules are model instructions, not deterministic guarantees.
The Foundry playground is useful for manual exploration but bypasses this client's
validation and does not display its terminal introduction.

## Run the dedicated demo lab

Prerequisites: Python **3.12**, Azure CLI with Foundry project creation and Search
`--knowledge-retrieval` support, and Azure permissions to create resources and assign
resource-scoped roles. The live session used Azure CLI 2.91.0.

```bash
git clone https://github.com/JeanneBM/azure-foundry-rag-agent.git
cd azure-foundry-rag-agent
python -m venv .venv
```

Activate the environment using the command for your shell:

| Shell | Command |
| --- | --- |
| Linux/macOS Bash | `source .venv/bin/activate` |
| Windows Git Bash | `source .venv/Scripts/activate` |
| Windows PowerShell | `.venv\Scripts\Activate.ps1` |

```bash
python -m pip install --require-hashes -r requirements.txt
python -m pip check
az login
python scripts/lab.py setup --subscription '<SUBSCRIPTION_ID>' --location swedencentral
python scripts/lab.py check
python scripts/lab.py smoke
python scripts/lab.py run
```

Run setup and checks one at a time; inspect any failure before continuing.
The dedicated lab loads its recorded configuration from `.local/`; it does not need
a manually configured `.env`. For an existing KB, follow the separate
[quickstart](docs/quickstart.md).

Setup provisions a dedicated Foundry account/project, `gpt-4.1-mini`, a Basic Search
service with one replica/partition, an index, two documents, a knowledge source,
a knowledge base and a project-managed-identity RemoteTool connection. Defaults are
`rg-foundry-rag-demo` and Sweden Central. Region, group, model, model version and
capacity can be changed with setup flags **before the first run**; availability and
quota depend on the subscription. The lab does not deploy AKS or a web application.

One-shot questions use the same guarded client:

```bash
python scripts/lab.py run --question "What are the support hours?"
```

Type `exit` to close the interactive chat. **This does not stop Azure billing.**

## Cost, state and cleanup

Basic Search remains billable while provisioned; model calls are metered.
Closing the terminal or playground does not delete the lab.

```bash
python scripts/lab.py delete --confirm rg-foundry-rag-demo
```

Deletion waits and verifies that the recorded group is absent. Local reports and state
are retained. Soft-deleted Cognitive Services accounts are not purged. Keep `.local/`
until cleanup completes: it records group ownership, subscription and resource names.
Setup can resume partial provisioning with the same parameters. It refuses to adopt
an unrelated group and does not silently roll back resources on failure.

Lab token acquisition is scoped to the recorded subscription without changing the
operator's global Azure CLI default. Existing resources outside the recorded lab
are not adopted or deleted.

## Versions and existing environments

`create_rag_agent.py` creates or reuses a version and writes an atomic local manifest.
Reuse compares the requested definition's fingerprint with the latest version's
`managed_by` and `config_sha256` metadata; server-added defaults do not create duplicates.
A changed definition or `--force` creates a candidate version.

Clients resolve `--version` → `AGENT_VERSION` → a matching local manifest, never
implicitly `latest`. Verify a candidate before moving other clients to it. Roll back
by selecting a previous verified version. Agent deletion is separate from lab cleanup;
see the [quickstart](docs/quickstart.md#rollback-and-cleanup).

For updates to the existing demo KB/connection or agent instructions:

```bash
git pull --ff-only
python scripts/lab.py repair-mcp
python scripts/lab.py smoke
```

Repair updates the dedicated demo KB to `minimal`/`extractiveData`, its MCP connection,
and the agent version/manifest. It does not recreate infrastructure or reindex documents.
In the playground, select the returned version and start a new conversation.

## Validation and current evidence

Offline verification:

```bash
python -m pip install --require-hashes -r requirements-dev.txt
python -m pip check
ruff check .
ruff format --check .
python -m pytest -q
```

Tests cover SDK serialization, version reuse, both MCP envelopes, citation rejection,
subscription isolation, telemetry and lab lifecycle/reporting. CI makes no live Azure
calls; [GitHub Actions](GITHUB_ACTIONS.md) documents its scope.

Azure setup and manual playground retrieval/refusal were exercised during development.
A successful playground answer does not establish a passing guarded CLI smoke test.
Sanitized evidence of a final CLI smoke PASS and a full delete/recreate cycle is not
included in this repository. Run `python scripts/lab.py smoke` to record your own
known-answer/citation and unknown-answer checks under `.local/reports/`.
Exit codes are **0 PASS**, **1 FAIL**, **2 INCONCLUSIVE**. See the
[validation guide](docs/lab-validation.md) for the optional two-generation cycle.

## Boundaries and telemetry

The KB connection provides shared document access. There is no per-user ACL passthrough,
automatic document ingestion, public HTTP API or production-scale evaluation here.
Use only a KB intended for all authorized users of this client. Requests use
`store=False` and do not create persistent Conversations; Azure retention is separate.

Telemetry is opt-in via `AGENT_TELEMETRY_FILE` (JSONL) or `AGENT_TELEMETRY_STDOUT=1`.
It records timing, tool names, reference IDs, native citation counts, available token
usage and outcomes. It excludes questions, answers, retrieved text, tool arguments
and argument hashes. Metadata is operational data, not anonymous data. No external
monitoring platform is required.

## API versions and references

| Contract | Lab API version |
| --- | --- |
| Search index and knowledge source | `2026-04-01` |
| Knowledge base configuration and MCP | `2026-08-01-preview` |
| RemoteTool connection management | `2025-10-01-preview` |

The KB/MCP and RemoteTool paths use preview APIs. This disposable public-endpoint,
synthetic-data lab is not a production deployment.

- [Connect Foundry to a knowledge base](https://learn.microsoft.com/en-us/azure/foundry/agents/how-to/foundry-iq-connect)
- [Search retrieval and MCP contracts](https://learn.microsoft.com/en-us/azure/search/agentic-retrieval-how-to-retrieve)
- [Foundry agent API reference](https://learn.microsoft.com/en-us/rest/api/microsoft-foundry/aiproject)
