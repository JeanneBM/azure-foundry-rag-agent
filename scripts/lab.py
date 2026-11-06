"""Provision, run, smoke-test and delete a dedicated Foundry RAG demo lab."""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

from lab_support import (
    LabError,
    az,
    child,
    delete,
    grant,
    load,
    owned_group,
    prepare,
    request,
    save,
)

ROOT = Path(__file__).resolve().parents[1]
SEARCH_API = "2026-04-01"
MCP_API = "2026-08-01-preview"
CONNECTION_API = "2025-10-01-preview"
AZURE_AI_USER_ROLE_ID = "53ca6127-db72-4b80-b1b0-d745d6d5456d"
DEMO_WELCOME = (
    "Welcome! I answer questions about product returns and support hours using the "
    "attached demo documents. I provide source citations and do not answer questions "
    "outside the knowledge base."
)


def configure_demo_kb(state, endpoint):
    # Preview defaults to low reasoning, which requires a KB model. This lab
    # deliberately uses Search-only retrieval and generates answers in Foundry.
    request(
        state,
        f"{endpoint}/knowledgebases('demo-kb')?api-version={MCP_API}",
        "PUT",
        {
            "name": "demo-kb",
            "knowledgeSources": [{"name": "demo-source"}],
            "retrievalReasoningEffort": {"kind": "minimal"},
            "outputMode": "extractiveData",
        },
    )


def setup(args):
    # Fail before provisioning if required CLI capabilities are unavailable.
    az("cognitiveservices", "account", "project", "create", "--help")
    search_help = az("search", "service", "create", "--help")
    if "--knowledge-retrieval" not in search_help:
        raise LabError("Upgrade Azure CLI: Search knowledge-retrieval support is required.")
    config = {
        "location": args.location,
        "model": args.model,
        "version": args.model_version,
        "capacity": args.capacity,
    }
    path, state = prepare(ROOT, "foundry-rag", args.subscription, args.group, config)
    subscription, group, name = (
        state["subscriptionId"],
        state["resourceGroup"],
        state["accountName"],
    )
    state["ready"] = False
    save(path, state)
    for provider in ("Microsoft.CognitiveServices", "Microsoft.Search"):
        az("provider", "register", "--namespace", provider, "--wait", subscription=subscription)
    print("[1/5] Foundry account, project and model")
    account = az(
        "cognitiveservices",
        "account",
        "create",
        "-n",
        name,
        "-g",
        group,
        "-l",
        args.location,
        "--kind",
        "AIServices",
        "--sku",
        "S0",
        "--custom-domain",
        name,
        "--assign-identity",
        "--allow-project-management",
        "true",
        "--yes",
        subscription=subscription,
    )
    project = az(
        "cognitiveservices",
        "account",
        "project",
        "create",
        "-n",
        name,
        "-g",
        group,
        "--project-name",
        "rag-demo",
        "-l",
        args.location,
        "--assign-identity",
        subscription=subscription,
    )
    az(
        "cognitiveservices",
        "account",
        "deployment",
        "create",
        "-n",
        name,
        "-g",
        group,
        "--deployment-name",
        "rag-model",
        "--model-name",
        args.model,
        "--model-version",
        args.model_version,
        "--model-format",
        "OpenAI",
        "--sku-name",
        "GlobalStandard",
        "--sku-capacity",
        str(args.capacity),
        subscription=subscription,
    )
    print("[2/5] Dedicated Basic Search (one replica/partition)")
    search_name = f"rag-search-{state['generation'][:10]}"
    search = az(
        "search",
        "service",
        "create",
        "-n",
        search_name,
        "-g",
        group,
        "-l",
        args.location,
        "--sku",
        "basic",
        "--replica-count",
        "1",
        "--partition-count",
        "1",
        # Entra ID only: every lab caller uses RBAC tokens, so API keys stay disabled.
        # disableLocalAuth cannot be combined with --auth-options/--aad-auth-failure-mode.
        "--disable-local-auth",
        "--semantic-search",
        "free",
        "--knowledge-retrieval",
        "free",
        subscription=subscription,
    )
    # Use project identity, not parent account identity, for the RemoteTool connection.
    project = az(
        "cognitiveservices",
        "account",
        "project",
        "show",
        "-n",
        name,
        "-g",
        group,
        "--project-name",
        "rag-demo",
        subscription=subscription,
    )
    principal = (project.get("identity") or {}).get("principalId")
    if not principal:
        raise LabError("Project has no system identity. Inspect it, then rerun setup.")
    token = az("account", "get-access-token", subscription=subscription)["accessToken"]
    # Decode only the signed-in principal identifier for RBAC; the token is never persisted.
    import base64

    claims = json.loads(base64.urlsafe_b64decode(token.split(".")[1] + "=="))
    user = claims.get("oid")
    if not user:
        raise LabError(
            "Signed-in token has no object ID. Use an Azure CLI user or service principal login."
        )
    kind = "ServicePrincipal" if claims.get("idtyp") == "app" else "User"
    # Built-in "Azure AI User" (shown as Foundry User). The role ID is stable across the rename.
    grant(state, user, AZURE_AI_USER_ROLE_ID, account["id"], kind)
    grant(state, user, "Search Service Contributor", search["id"], kind)
    grant(state, user, "Search Index Data Contributor", search["id"], kind)
    grant(state, principal, "Search Index Data Reader", search["id"])
    endpoint = f"https://{search_name}.search.windows.net"
    print("[3/5] Index and synthetic documents")
    index = {
        "name": "demo-docs",
        "fields": [
            {"name": "id", "type": "Edm.String", "key": True, "filterable": True},
            {"name": "title", "type": "Edm.String", "searchable": True},
            {"name": "content", "type": "Edm.String", "searchable": True},
        ],
        "semantic": {
            "defaultConfiguration": "demo-semantic",
            "configurations": [
                {
                    "name": "demo-semantic",
                    "prioritizedFields": {
                        "titleField": {"fieldName": "title"},
                        "prioritizedContentFields": [{"fieldName": "content"}],
                    },
                }
            ],
        },
    }
    request(state, f"{endpoint}/indexes/demo-docs?api-version={SEARCH_API}", "PUT", index)
    documents = json.loads((ROOT / "examples/lab-documents.json").read_text(encoding="utf-8"))
    indexed = request(
        state,
        f"{endpoint}/indexes/demo-docs/docs/index?api-version={SEARCH_API}",
        "POST",
        {"value": [{"@search.action": "mergeOrUpload", **doc} for doc in documents]},
    )
    if any(not result.get("status") for result in indexed["value"]):
        raise LabError("One or more demo documents failed indexing. Rerun setup.")
    print("[4/5] Knowledge source, base and managed-identity MCP connection")
    source = {
        "name": "demo-source",
        "kind": "searchIndex",
        "searchIndexParameters": {
            "searchIndexName": "demo-docs",
            "semanticConfigurationName": "demo-semantic",
            "sourceDataFields": [{"name": "title"}, {"name": "content"}],
            "searchFields": [{"name": "content"}],
        },
    }
    request(
        state, f"{endpoint}/knowledgesources('demo-source')?api-version={SEARCH_API}", "PUT", source
    )
    configure_demo_kb(state, endpoint)
    mcp = f"{endpoint}/knowledgebases/demo-kb/mcp?api-version={MCP_API}"
    request(
        state,
        f"https://management.azure.com{project['id']}/connections/demo-kb-mcp?api-version={CONNECTION_API}",
        "PUT",
        {
            "name": "demo-kb-mcp",
            "properties": {
                "authType": "ProjectManagedIdentity",
                "category": "RemoteTool",
                "target": mcp,
                "isSharedToAll": True,
                "audience": "https://search.azure.com/",
                "metadata": {"ApiType": "Azure"},
            },
        },
        audience="https://management.azure.com/",
    )
    state["environment"] = {
        "PROJECT_ENDPOINT": project["properties"]["endpoints"]["AI Foundry API"],
        "RAG_MCP_ENDPOINT": mcp,
        "PROJECT_CONNECTION_NAME": "demo-kb-mcp",
        "MODEL_DEPLOYMENT": "rag-model",
        "AGENT_NAME": "RagDemo",
        "AGENT_VERSION": "",
        "AZURE_CREDENTIAL_MODE": "cli",
        "DEPLOYMENT_FILE": str(ROOT / ".local/deployment.json"),
    }
    state["ready"] = True
    save(path, state)
    print("[5/5] Create/reuse agent version")
    result = child(ROOT, state, ["create_rag_agent.py"])
    if result:
        state["ready"] = False
        save(path, state)
        raise LabError("Agent deployment failed. Retain state; rerun setup or delete the lab.")
    print("SETUP COMPLETE. Run python scripts/lab.py smoke to verify live retrieval and answers.")
    print("Basic Search remains billable until python scripts/lab.py delete completes.")


def repair_mcp():
    """Update the existing connection and agent without provisioning infrastructure."""
    path, state = load(ROOT)
    owned_group(state)
    if not state.get("environment"):
        raise LabError("No configured lab environment. Complete setup first.")
    project = az(
        "cognitiveservices",
        "account",
        "project",
        "show",
        "-n",
        state["accountName"],
        "-g",
        state["resourceGroup"],
        "--project-name",
        "rag-demo",
        subscription=state["subscriptionId"],
    )
    endpoint = f"https://rag-search-{state['generation'][:10]}.search.windows.net"
    mcp = f"{endpoint}/knowledgebases/demo-kb/mcp?api-version={MCP_API}"
    state["ready"] = False
    save(path, state)
    configure_demo_kb(state, endpoint)
    request(
        state,
        f"https://management.azure.com{project['id']}/connections/demo-kb-mcp?api-version={CONNECTION_API}",
        "PUT",
        {
            "name": "demo-kb-mcp",
            "properties": {
                "authType": "ProjectManagedIdentity",
                "category": "RemoteTool",
                "target": mcp,
                "isSharedToAll": True,
                "audience": "https://search.azure.com/",
                "metadata": {"ApiType": "Azure"},
            },
        },
        audience="https://management.azure.com/",
    )
    state["environment"]["RAG_MCP_ENDPOINT"] = mcp
    state["environment"]["AGENT_VERSION"] = ""
    save(path, state)
    # The connection is configured, but persisted readiness stays false until
    # agent deployment succeeds. Allow only this deployment child to proceed.
    if child(ROOT, {**state, "ready": True}, ["create_rag_agent.py"]):
        raise LabError("Agent update failed. Retain state and rerun repair-mcp.")
    state["ready"] = True
    save(path, state)
    print("Minimal retrieval, MCP connection and agent updated. Run python scripts/lab.py smoke.")


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    commands = parser.add_subparsers(dest="action", required=True)
    provision = commands.add_parser("setup", help="Create billable resources in a dedicated group")
    provision.add_argument("--subscription", required=True)
    provision.add_argument("--group", default="rg-foundry-rag-demo")
    provision.add_argument("--location", default="swedencentral")
    provision.add_argument("--model", default="gpt-4.1-mini")
    provision.add_argument("--model-version", default="2025-04-14")
    provision.add_argument("--capacity", type=int, choices=range(1, 101), default=10)
    commands.add_parser("smoke", help="Run known/unknown questions against synthetic documents")
    commands.add_parser("repair-mcp", help="Update existing MCP connection and agent only")
    run = commands.add_parser("run", help="Start the interactive CLI; exit stops the local client")
    run.add_argument("--question")
    commands.add_parser(
        "check", help="Read-only check of the recorded group's ownership and setup state"
    )
    cleanup = commands.add_parser("delete", help="Delete and verify the dedicated resource group")
    cleanup.add_argument("--confirm", help="Exact recorded resource-group name (noninteractive)")
    args = parser.parse_args()
    if args.action == "repair-mcp":
        repair_mcp()
        return 0
    if args.action == "setup":
        setup(args)
        return 0
    if args.action == "delete":
        delete(ROOT, args.confirm)
        return 0
    if args.action == "smoke":
        import subprocess

        return subprocess.call([sys.executable, "scripts/validate_lab.py", "smoke"], cwd=ROOT)
    _, state = load(ROOT)
    if args.action == "check":
        owned_group(state)
        print(f"Recorded group ownership verified; setup complete: {state.get('ready', False)}")
        return 0
    # Demo-specific introduction; not persisted, so existing lab state needs no repair.
    # child() still refuses partial setup before using this environment.
    environment = {**state.get("environment", {}), "CHAT_WELCOME": DEMO_WELCOME}
    chat_state = {**state, "environment": environment}
    return child(
        ROOT, chat_state, ["chat.py", *(["--question", args.question] if args.question else [])]
    )


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except (LabError, OSError, KeyError, ValueError) as exc:
        print(
            str(exc)
            if isinstance(exc, LabError)
            else "Lab operation failed; check local state and configuration.",
            file=sys.stderr,
        )
        raise SystemExit(1) from None
    except KeyboardInterrupt:
        print(
            "Interrupted. Resources are retained; use delete after saving evidence.",
            file=sys.stderr,
        )
        raise SystemExit(130) from None
