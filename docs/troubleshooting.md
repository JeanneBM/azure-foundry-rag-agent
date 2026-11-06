# Troubleshooting the demo lab

Run commands from the repository root with its virtual environment active.
Keep `.local/` until cleanup completes. An unsuccessful request is not evidence
that the model correctly refused a question.

## Existing lab updates

```bash
git pull --ff-only
python scripts/lab.py repair-mcp
```

Repair reconfigures the **dedicated demo** KB to `minimal` reasoning and
`extractiveData`, updates its MCP connection and creates or reuses the agent
version. It does not reindex documents. It is not a repair command for arbitrary
external knowledge bases. In the playground, select the reported version and
start a new conversation. Model instruction changes do not take effect in an
older immutable version.

## Common symptoms

| Symptom | Meaning / check |
| --- | --- |
| `missing_citations` | The response has no accepted inline ID or validated native URL citation. Do not count this as an answer. |
| `unknown_citation` | A cited ID or URL is absent from the current retrieval. |
| `ambiguous_citation_url` | A native URL matches multiple retrieved records; use exact `[ref_id:X]` citations. |
| `unsupported_retrieval_format` | MCP returned an unknown envelope. Supported formats are `ref_id`/`content` records and `documents`/`id`; do not interpret an unknown payload as empty evidence. |
| `multiple_retrieval_calls` | The response contains more than one KB call. Start a fresh conversation with the current agent version; the validator does not merge call-local IDs. |
| API version rejected by MCP | Verify that the agent URL and RemoteTool connection use the same supported preview version. |
| KB model required for reasoning | The model-free demo requires explicit `minimal` reasoning and `extractiveData`. Preview otherwise defaults to `low`. |
| `Setup is incomplete` | Preserve state, inspect the preceding failure, and rerun the same setup parameters or `repair-mcp` for an already configured demo. |
| Playground works but terminal rejects the answer | The playground bypasses the Python validation gate. Check the selected agent version, retrieval output and citation metadata. |

## Read the report

```bash
python scripts/lab.py smoke
```

The command prints the report path. Read that specific `report.md` and linked
phase evidence. `0` means PASS, `1` FAIL, `2` INCONCLUSIVE. The report contains no
raw model answers or retrieved document text; phase reasons indicate validation
failures. SDK/network exceptions can appear as `execution_or_evidence_error`.
Do not share tokens, `.env` or unreviewed raw Azure responses while diagnosing.

## Cleanup

Closing the chat does not stop Search billing. When finished:

```bash
python scripts/lab.py delete --confirm rg-foundry-rag-demo
```

The command verifies that the recorded group is absent and retains local reports.
