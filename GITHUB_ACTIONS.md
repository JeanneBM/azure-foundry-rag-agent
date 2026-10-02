# GitHub Actions: offline validation only

The workflow in `.github/workflows/ci.yml` runs lint, formatting, dependency checks and offline tests on pushes and PRs to `main`. A manual workflow dispatch runs the same checks.

## Access and scope

- The workflow has only `contents: read` permission.
- It does not log in to Azure or request an OIDC token.
- It does not use Azure secrets, project endpoints or deployment variables.
- It does not create, update or delete Azure resources.
- It does not run `create_rag_agent.py`, `chat.py`, `delete_rag_agent.py` or the live `smoke_test.py`.
- Tests use mock transports and responses; they do not call your Azure services.

Installing dependencies uses the package registry. Offline here means no live Azure calls during validation.

## Local checks

```bash
python -m pip install --require-hashes -r requirements-dev.txt
python -m pip check
ruff check .
ruff format --check .
python -m pytest -q
```

## Deploy from your own machine

Configure your local `.env`, log in with `az login` and run `python create_rag_agent.py` yourself. Then run `smoke_test.py` with questions tailored to your KB. The live smoke test contacts Azure only when you explicitly run it locally.

The script writes the candidate version to local `deployment.json`. After verification, retain the manifest and set `AGENT_VERSION` in client environments. Rollback selects a previous verified version. Full instructions are in [README.md](README.md).

## Remove previous GitHub-to-Azure access

If you previously configured GitHub OIDC for this repository, remove its federated credential from the corresponding Entra App Registration or Managed Identity. Do not remove credentials used by other applications.

Remove repository/environment secrets and variables created solely for the former Azure deployment workflow. Existing credentials are not deleted by changing this workflow; their removal must be performed in GitHub and Azure settings. This change does not modify Azure configuration.
