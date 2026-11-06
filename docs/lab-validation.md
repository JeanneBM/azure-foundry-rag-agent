# Individual lab validation report

This repository produces its **own** report. There is no cross-repository runner
or combined report. Reports use schema `1.0` and the verdict semantics below. Assertions cover this
Foundry RAG lab only.

## Existing lab: smoke

From this repository's root, after its setup and dependency installation:

```sh
python scripts/validate_lab.py smoke
```

Smoke checks: Known answer (30 days) with validated citations, and abstention for an unknown question against the synthetic dedicated-lab documents.

The existing lab remains provisioned after smoke, including after failure.
A readiness failure prevents model requests. Run `python scripts/lab.py delete`
after saving the report and evidence.

## Dedicated lab: full cycle

The target group must initially be absent. This command creates billable Azure
resources, tests generation 1, deletes and verifies it, recreates with fresh
resource names, tests generation 2, then deletes and verifies it again:

```sh
python scripts/validate_lab.py cycle --subscription '<YOUR_SUBSCRIPTION_ID>' --confirm-delete rg-foundry-rag-demo
```

The group name is explicit consent for this command's two cleanup operations.
A pre-existing group is refused; cycle mode does not delete an existing lab to
make room. Keep the recorded `.local/` state and cleanup inventory. Cleanup is
attempted after partial setup, test failures and interruption. Failed cleanup
prevents recreation. Inspect the report and rerun the normal cleanup script if
verification fails. Check region/model/SKU availability and permissions first.
Cycle uses the setup defaults; use smoke for an existing customized lab.

## Files and verdicts

Each execution writes `.local/reports/<UTC-run-id>/report.json` and `report.md`
in **this checkout**, with phase evidence in the same run directory. Reports
link local evidence and include UTC times, durations, assertions and verdicts.
They survive cleanup and are separate from scenario/evaluation evidence.

| Verdict | Meaning | Exit code |
| --- | --- | ---: |
| PASS | All requested phases completed and all smoke assertions passed; cycle also verified both deletions and fresh resource names. | 0 |
| FAIL | Observed evidence violates an assertion (for example wrong return period, invalid citations, failure to abstain, reused resource names or incomplete cleanup). | 1 |
| INCONCLUSIVE | Execution, prerequisites, networking or evidence collection prevented a determination; not a pass. | 2 |

A smoke PASS verifies that smoke's limited scenario, not production readiness or
all evaluation scenarios. A report produced during an offline mocked test is
not live Azure evidence. The new lifecycle must still be run on Azure; no live
result is implied by the presence of these scripts. Raw logs and SDK/evaluation
evidence remain local and must be reviewed before sharing.

Lab children acquire CLI tokens for the recorded subscription using
`AZURE_CLI_SUBSCRIPTION`. They do not call `az account set`.
Multiple retrieval calls produce `multiple_retrieval_calls`; validation errors are
not counted as successful abstentions. MCP uses preview `2026-08-01-preview`;
index/source provisioning uses GA `2026-04-01`. The dedicated knowledge base uses
preview `2026-08-01-preview` with explicit `minimal` reasoning and `extractiveData`
so retrieval does not require a KB model.
