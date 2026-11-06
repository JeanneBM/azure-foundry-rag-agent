"""Exercise the complete provisioning plan without Azure or model calls."""

import base64
import importlib.util
import json
from argparse import Namespace
from pathlib import Path

import pytest


def test_setup_wires_project_identity_search_payloads_and_isolated_manifest(tmp_path, monkeypatch):
    scripts = Path(__file__).resolve().parents[1] / "scripts"
    monkeypatch.syspath_prepend(str(scripts))
    spec = importlib.util.spec_from_file_location("rag_lab_setup", scripts / "lab.py")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    monkeypatch.setattr(module, "ROOT", tmp_path)
    (tmp_path / "examples").mkdir()
    (tmp_path / "examples/lab-documents.json").write_text(
        '[{"id":"one","title":"Demo","content":"30 days"}]'
    )
    state = {
        "subscriptionId": "sub",
        "resourceGroup": "rg-demo",
        "accountName": "foundry-demo",
        "generation": "a" * 32,
        "config": {},
    }
    path = tmp_path / ".local/lab.json"
    monkeypatch.setattr(module, "prepare", lambda *args: (path, state))
    calls, requests, roles, children = [], [], [], []
    claims = base64.urlsafe_b64encode(json.dumps({"oid": "operator"}).encode()).decode().rstrip("=")

    def az(*args, **kwargs):
        calls.append(args)
        if "--help" in args:
            return "--knowledge-retrieval"
        if args[:3] == ("account", "get-access-token"):
            return {"accessToken": f"header.{claims}.signature"}
        if args[:2] == ("account", "get-access-token"):
            return {"accessToken": f"header.{claims}.signature"}
        if args[:3] == ("cognitiveservices", "account", "project"):
            return {
                "id": "/project",
                "identity": {"principalId": "project-identity"},
                "properties": {
                    "endpoints": {"AI Foundry API": "https://demo/api/projects/rag-demo"}
                },
            }
        if args[:2] == ("cognitiveservices", "account"):
            return {"id": "/account", "identity": {"principalId": "parent-identity"}}
        if args[:2] == ("search", "service"):
            return {"id": "/search"}
        return {}

    def request(state, url, method="GET", payload=None, **kwargs):
        requests.append((url, method, payload, kwargs))
        return {"value": [{"status": True}]}

    monkeypatch.setattr(module, "az", az)
    monkeypatch.setattr(module, "request", request)
    monkeypatch.setattr(module, "grant", lambda *args: roles.append(args))
    monkeypatch.setattr(module, "child", lambda *args: children.append(args) or 0)
    module.setup(
        Namespace(
            subscription="sub",
            group="rg-demo",
            location="swedencentral",
            model="gpt-4.1-mini",
            model_version="2025-04-14",
            capacity=10,
        )
    )
    assert state["ready"]
    assert any(role[1:3] == ("project-identity", "Search Index Data Reader") for role in roles)
    assert not any(role[1] == "parent-identity" for role in roles)
    connection = next(item for item in requests if "/connections/" in item[0])
    assert connection[2]["properties"]["target"] == state["environment"]["RAG_MCP_ENDPOINT"]
    assert connection[2]["properties"]["authType"] == "ProjectManagedIdentity"
    kb = next(item for item in requests if "/knowledgebases('demo-kb')?" in item[0])
    assert kb[0].endswith("api-version=2026-08-01-preview")
    assert kb[2]["retrievalReasoningEffort"] == {"kind": "minimal"}
    assert kb[2]["outputMode"] == "extractiveData"
    assert "models" not in kb[2]
    assert connection[2]["properties"]["target"].endswith("api-version=2026-08-01-preview")
    assert any("/indexes/demo-docs?api-version=2026-04-01" in item[0] for item in requests)
    assert state["environment"]["DEPLOYMENT_FILE"] == str(tmp_path / ".local/deployment.json")
    assert state["environment"]["AGENT_VERSION"] == ""
    assert children[0][2] == ["create_rag_agent.py"]
    assert all(
        "--knowledge-retrieval" in cmd
        for cmd in calls
        if cmd[:3] == ("search", "service", "create") and "--help" not in cmd
    )
    search_create = next(
        cmd for cmd in calls if cmd[:3] == ("search", "service", "create") and "--help" not in cmd
    )
    # Entra ID only: keys disabled, and no auth option that would re-enable them.
    assert "--disable-local-auth" in search_create
    assert "--auth-options" not in search_create
    assert "--aad-auth-failure-mode" not in search_create
    assert json.loads(path.read_text())["ready"]


@pytest.mark.parametrize("child_result", [0, 1])
def test_repair_mcp_updates_kb_connection_and_agent(tmp_path, monkeypatch, child_result):
    scripts = Path(__file__).resolve().parents[1] / "scripts"
    monkeypatch.syspath_prepend(str(scripts))
    spec = importlib.util.spec_from_file_location("rag_lab_repair", scripts / "lab.py")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    monkeypatch.setattr(module, "ROOT", tmp_path)
    path = tmp_path / ".local/lab.json"
    state = {
        "subscriptionId": "sub",
        "resourceGroup": "rg-demo",
        "accountName": "foundry-demo",
        "generation": "a" * 32,
        "ready": True,
        "environment": {"RAG_MCP_ENDPOINT": "old", "AGENT_VERSION": "1"},
    }
    calls, requests = [], []
    monkeypatch.setattr(module, "load", lambda _: (path, state))
    monkeypatch.setattr(module, "owned_group", lambda _: None)

    def az(*args, **kwargs):
        calls.append(args)
        assert args[:4] == ("cognitiveservices", "account", "project", "show")
        return {"id": "/project"}

    monkeypatch.setattr(module, "az", az)
    monkeypatch.setattr(module, "request", lambda *args, **kwargs: requests.append(args))

    def deploy_child(root, child_state, args):
        assert child_state["ready"] is True
        assert json.loads(path.read_text())["ready"] is False
        assert args == ["create_rag_agent.py"]
        return child_result

    monkeypatch.setattr(module, "child", deploy_child)
    if child_result:
        with pytest.raises(module.LabError, match="Agent update failed"):
            module.repair_mcp()
    else:
        module.repair_mcp()
    assert len(calls) == 1 and len(requests) == 2
    assert "/knowledgebases('demo-kb')?" in requests[0][1]
    assert requests[0][3]["retrievalReasoningEffort"] == {"kind": "minimal"}
    assert requests[0][3]["outputMode"] == "extractiveData"
    assert "models" not in requests[0][3]
    assert "/connections/demo-kb-mcp?" in requests[1][1]
    target = requests[1][3]["properties"]["target"]
    assert target.endswith("/knowledgebases/demo-kb/mcp?api-version=2026-08-01-preview")
    assert state["environment"]["RAG_MCP_ENDPOINT"] == target
    assert state["environment"]["AGENT_VERSION"] == ""
    assert json.loads(path.read_text())["ready"] is (child_result == 0)


def test_run_passes_demo_welcome_without_persisting_it(tmp_path, monkeypatch):
    scripts = Path(__file__).resolve().parents[1] / "scripts"
    monkeypatch.syspath_prepend(str(scripts))
    spec = importlib.util.spec_from_file_location("rag_lab_run", scripts / "lab.py")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    state = {"ready": True, "environment": {"AGENT_NAME": "RagDemo"}}
    children = []
    monkeypatch.setattr(module, "load", lambda _: (tmp_path / ".local/lab.json", state))
    monkeypatch.setattr(module, "child", lambda *args: children.append(args) or 0)
    monkeypatch.setattr(module.sys, "argv", ["lab.py", "run", "--question", "Q"])
    assert module.main() == 0
    _, child_state, args = children[0]
    assert child_state["environment"]["CHAT_WELCOME"] == module.DEMO_WELCOME
    assert args == ["chat.py", "--question", "Q"]
    assert "CHAT_WELCOME" not in state["environment"]


def test_run_with_partial_setup_reports_incomplete_setup(tmp_path, monkeypatch):
    scripts = Path(__file__).resolve().parents[1] / "scripts"
    monkeypatch.syspath_prepend(str(scripts))
    spec = importlib.util.spec_from_file_location("rag_lab_partial_run", scripts / "lab.py")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    state = {"ready": False}
    monkeypatch.setattr(module, "load", lambda _: (tmp_path / ".local/lab.json", state))
    # child() lives in lab_support and checks ownership there before readiness.
    monkeypatch.setattr(module.sys.modules["lab_support"], "owned_group", lambda _: None)
    monkeypatch.setattr(module.sys, "argv", ["lab.py", "run"])
    with pytest.raises(module.LabError, match="Setup is incomplete"):
        module.main()
