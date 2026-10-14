"""Exercise the complete provisioning plan without Azure or model calls."""

import base64
import importlib.util
import json
from argparse import Namespace
from pathlib import Path


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
    assert state["environment"]["DEPLOYMENT_FILE"] == str(tmp_path / ".local/deployment.json")
    assert state["environment"]["AGENT_VERSION"] == ""
    assert children[0][2] == ["create_rag_agent.py"]
    assert all(
        "--knowledge-retrieval" in cmd
        for cmd in calls
        if cmd[:3] == ("search", "service", "create") and "--help" not in cmd
    )
    assert json.loads(path.read_text())["ready"]
