import json

import pytest

from rag_foundry.config import Settings


@pytest.fixture
def settings(monkeypatch, tmp_path):
    monkeypatch.chdir(tmp_path)
    for key in (
        "PROJECT_ENDPOINT",
        "RAG_MCP_ENDPOINT",
        "PROJECT_CONNECTION_NAME",
        "AGENT_NAME",
        "MODEL_DEPLOYMENT",
        "AGENT_VERSION",
        "DEPLOYMENT_FILE",
        "AZURE_CREDENTIAL_MODE",
        "MANAGED_IDENTITY_CLIENT_ID",
        "REQUEST_TIMEOUT_SECONDS",
        "MAX_OUTPUT_TOKENS",
        "MAX_QUESTION_CHARS",
        "HISTORY_TURNS",
    ):
        monkeypatch.delenv(key, raising=False)
    monkeypatch.setenv(
        "PROJECT_ENDPOINT", "https://example.services.ai.azure.com/api/projects/test"
    )
    monkeypatch.setenv(
        "RAG_MCP_ENDPOINT",
        "https://example.search.windows.net/knowledgebases/docs/mcp?api-version=2026-04-01",
    )
    monkeypatch.setenv("PROJECT_CONNECTION_NAME", "kb-connection")
    return Settings.from_env(deployment=True)


def response_payload(text="Policy is 30 days. [ref_id:0]", records=None):
    if records is None:
        records = [{"ref_id": "0", "title": "Return policy", "content": "Return within 30 days."}]
    return {
        "id": "resp_test",
        "object": "response",
        "created_at": 1,
        "model": "gpt-4.1-mini",
        "status": "completed",
        "error": None,
        "incomplete_details": None,
        "output": [
            {
                "id": "mcp_test",
                "type": "mcp_call",
                "server_label": "KnowledgeBase",
                "name": "knowledge_base_retrieve",
                "arguments": "{}",
                "output": json.dumps(records),
                "error": None,
                "status": "completed",
            },
            {
                "id": "msg_test",
                "type": "message",
                "role": "assistant",
                "status": "completed",
                "content": [{"type": "output_text", "text": text, "annotations": []}],
            },
        ],
        "parallel_tool_calls": False,
        "tool_choice": "auto",
        "tools": [],
    }
