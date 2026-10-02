import pytest

from rag_foundry.config import ConfigError, Settings


def test_missing_config_is_actionable(settings, monkeypatch):
    monkeypatch.delenv("PROJECT_ENDPOINT")
    with pytest.raises(ConfigError, match="PROJECT_ENDPOINT"):
        Settings.from_env()


@pytest.mark.parametrize(
    "name,value",
    [
        ("PROJECT_ENDPOINT", "http://example/api/projects/test"),
        ("PROJECT_ENDPOINT", "https://secret@example.com/api/projects/test"),
        ("PROJECT_ENDPOINT", "https://example.com/wrong"),
        ("PROJECT_ENDPOINT", "https://example.com/api/projects/test?token=secret"),
        ("RAG_MCP_ENDPOINT", "https://example.com/not-a-kb"),
        ("RAG_MCP_ENDPOINT", "https://example.com/knowledgebases/docs/mcp?api-version="),
        (
            "RAG_MCP_ENDPOINT",
            "https://example.com/knowledgebases/docs/mcp?api-version=2026-04-01&api-key=secret",
        ),
        ("AGENT_VERSION", "latest"),
        ("AGENT_VERSION", "0"),
        ("AGENT_NAME", "../other"),
        ("REQUEST_TIMEOUT_SECONDS", "0"),
        ("MAX_OUTPUT_TOKENS", "many"),
        ("HISTORY_TURNS", "-1"),
        ("AZURE_CREDENTIAL_MODE", "anything"),
        ("MODEL_DEPLOYMENT", " "),
    ],
)
def test_invalid_configuration(settings, monkeypatch, name, value):
    monkeypatch.setenv(name, value)
    with pytest.raises(ConfigError):
        Settings.from_env(deployment=True)


def test_environment_wins_over_dotenv(settings, monkeypatch):
    from pathlib import Path

    Path(".env").write_text("AGENT_NAME=FromFile\n", encoding="utf-8")
    monkeypatch.setenv("AGENT_NAME", "FromEnvironment")
    assert Settings.from_env().agent_name == "FromEnvironment"


def test_chat_does_not_require_deployment_settings(settings, monkeypatch):
    monkeypatch.delenv("RAG_MCP_ENDPOINT")
    monkeypatch.delenv("PROJECT_CONNECTION_NAME")
    assert Settings.from_env().project_endpoint == settings.project_endpoint
