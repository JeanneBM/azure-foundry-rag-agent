"""Azure CLI token acquisition is scoped without changing its global default."""

import importlib.util
import json
from dataclasses import replace
from pathlib import Path
from unittest.mock import patch

from rag_foundry.clients import make_credential


def test_cli_credential_passes_subscription_to_real_sdk_token_command(settings):
    scoped = replace(settings, credential_mode="cli", cli_subscription="recorded-sub")
    with make_credential(scoped) as credential:
        with patch("azure.identity._credentials.azure_cli._run_command") as run:
            run.return_value = json.dumps({"accessToken": "offline", "expires_on": 9999999999})
            assert credential.get_token("https://ai.azure.com/.default").token == "offline"
        command = run.call_args.args[0]
        assert command[command.index("--subscription") + 1] == "recorded-sub"
        assert command[:2] == ["account", "get-access-token"]


def test_smoke_environment_does_not_change_azure_default(monkeypatch):
    scripts = Path(__file__).resolve().parents[1] / "scripts"
    monkeypatch.syspath_prepend(str(scripts))
    spec = importlib.util.spec_from_file_location("scope_validation", scripts / "lab_validation.py")
    module = importlib.util.module_from_spec(spec)
    import sys

    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    monkeypatch.setenv("AZURE_CLI_SUBSCRIPTION", "unrelated")
    monkeypatch.setattr(
        module,
        "azure",
        lambda *a, **k: (_ for _ in ()).throw(
            AssertionError("Environment selection must not invoke Azure CLI")
        ),
    )
    env = module.selected_environment({"subscriptionId": "recorded", "environment": {}})
    assert env["AZURE_CLI_SUBSCRIPTION"] == "recorded"
    assert env["AZURE_CREDENTIAL_MODE"] == "cli"
    import os

    assert os.environ["AZURE_CLI_SUBSCRIPTION"] == "unrelated"
