# GitHub Actions: validation and deployment through OIDC

The workflow in `.github/workflows/ci.yml` runs validation on pushes and PRs to `main`. Deployment is manual: Actions → Validate and deploy Foundry RAG → Run workflow → select the `main` branch → enable `deploy`.

## One-time setup

1. Create an App Registration and Service Principal in Microsoft Entra ID for this repository.
2. Add a federated credential with the following values:

   | Field | Value |
   |---|---|
   | Issuer | `https://token.actions.githubusercontent.com` |
   | Subject | `repo:JeanneBM/jb-foundry-rag-agent:environment:production` |
   | Audience | `api://AzureADTokenExchange` |

3. Grant the principal permissions to manage agents and invoke the model in the target Foundry resource, according to your organization's RBAC policy. CI does not create resource groups or services, so it does not require a broad Contributor role for provisioning.
4. Configure the RemoteTool connection's Search access separately. The CI identity and the agent connection identity use separate authentication paths.
5. Create a GitHub Environment named `production`, allow the `main` branch and configure required reviewers if your organization's process requires them.
6. Add the following secrets and variables to that environment. Do not add a client secret — authentication uses OIDC.

After renaming the repository, update any existing Entra federated credential to use the subject above. A credential configured for the previous repository name will not match tokens issued for the renamed repository.

| GitHub Environment secret | Value |
|---|---|
| `AZURE_CLIENT_ID` | App Registration client ID |
| `AZURE_TENANT_ID` | Tenant ID |
| `AZURE_SUBSCRIPTION_ID` | Subscription ID |

| GitHub Environment variable | Value |
|---|---|
| `PROJECT_ENDPOINT` | Target Foundry project endpoint |
| `RAG_MCP_ENDPOINT` | Full endpoint of the existing KB |
| `PROJECT_CONNECTION_NAME` | RemoteTool connection name |
| `AGENT_NAME` | Optional; defaults to RagAgent |
| `MODEL_DEPLOYMENT` | Optional; defaults to gpt-4.1-mini |
| `SMOKE_KNOWN_QUESTION` | A question with a known answer in the KB |
| `SMOKE_EXPECTED_SUBSTRING` | A nonempty substring of the expected answer |
| `SMOKE_UNKNOWN_QUESTION` | A question the KB cannot answer |

Test questions stored in variables should be suitable for storage in GitHub configuration. The script does not print answers or documents to the deployment log.

For private endpoints, replace the `ubuntu-latest` runner with one that can access the Foundry network. Foundry → Search connectivity must work independently of the runner.

## Deployment flow

- Lint, formatting, offline tests and `pip check` must pass first.
- The deployment job obtains an OIDC token only after the Environment rules are satisfied.
- Required variables are checked before creating the agent.
- Runtime dependencies are installed using the versions and hashes in `requirements.txt`.
- The script creates or reuses a candidate version.
- Two tests against the real KB check a sourced answer and an unknown-answer case.
- Only after success is the `foundry-rag-release-<commit SHA>` artifact saved with `deployment.json`, retained for 90 days.

Deployment jobs run sequentially; a new deployment does not interrupt one already running. There is no automatic deployment on push or deletion of versions after a failed test.

## Client promotion and rollback

Download the manifest from a successful run. Set its `agent_version` as `AGENT_VERSION` in client environments, or provide the manifest to a client with a matching endpoint and agent name. Retain the previous manifest outside the temporary runner. A GitHub artifact does not replace a durable release registry.

Deployment creates an agent resource in Foundry; **it does not automatically update client environments**. Rollback switches clients to the previous verified version. Other versions remain in Azure.

A failed smoke test prevents the verified artifact from being saved. The candidate may already exist in Azure and be `latest`, so production integrations must pin a version. After a provisioning request fails, inspect the state in Azure before retrying manually.

## Local checks

```bash
python -m pip install --require-hashes -r requirements-dev.txt
python -m pip check
ruff check .
ruff format --check .
python -m pytest -q
```

Service documentation: [Azure login through OIDC](https://learn.microsoft.com/en-us/azure/developer/github/connect-from-azure-openid-connect), [Foundry RBAC](https://learn.microsoft.com/en-us/azure/foundry/concepts/rbac-foundry).
