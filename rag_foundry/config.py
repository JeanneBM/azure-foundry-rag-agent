"""Validated configuration shared by all commands."""

from __future__ import annotations

import os
import re
from dataclasses import dataclass
from pathlib import Path
from urllib.parse import parse_qs, urlsplit

from dotenv import load_dotenv


class ConfigError(ValueError):
    """An actionable configuration error, safe to display to the operator."""


def _value(name: str, default: str = "") -> str:
    return os.getenv(name, default).strip()


def _integer(name: str, default: int, low: int, high: int) -> int:
    try:
        value = int(_value(name, str(default)))
    except ValueError as exc:
        raise ConfigError(f"{name} must be an integer.") from exc
    if not low <= value <= high:
        raise ConfigError(f"{name} must be between {low} and {high}.")
    return value


def _https_url(name: str, value: str):
    try:
        parts = urlsplit(value)
        valid = (
            parts.scheme == "https"
            and parts.hostname
            and not parts.username
            and not parts.password
            and parts.port in (None, 443)
            and not parts.fragment
            and not any(c.isspace() for c in value)
            and "<" not in value
            and ">" not in value
        )
    except ValueError as exc:
        raise ConfigError(f"{name} must be a valid HTTPS URL.") from exc
    if not valid:
        raise ConfigError(f"{name} must be a valid HTTPS URL without credentials.")
    return parts


@dataclass(frozen=True)
class Settings:
    project_endpoint: str
    agent_name: str
    agent_version: str
    model_deployment: str
    rag_mcp_endpoint: str
    project_connection_name: str
    credential_mode: str
    managed_identity_client_id: str
    timeout_seconds: int
    max_output_tokens: int
    max_question_chars: int
    history_turns: int
    deployment_file: Path

    @classmethod
    def from_env(cls, *, deployment: bool = False) -> Settings:
        # Explicit path; don't search parents for unrelated .env files.
        load_dotenv(Path.cwd() / ".env", override=False)
        required = ["PROJECT_ENDPOINT"]
        if deployment:
            required += ["RAG_MCP_ENDPOINT", "PROJECT_CONNECTION_NAME"]
        missing = [name for name in required if not _value(name)]
        if missing:
            raise ConfigError("Missing configuration: " + ", ".join(missing))

        endpoint = _value("PROJECT_ENDPOINT").rstrip("/")
        parts = _https_url("PROJECT_ENDPOINT", endpoint)
        if not re.fullmatch(r"/api/projects/[^/]+", parts.path) or parts.query:
            raise ConfigError("PROJECT_ENDPOINT must end with /api/projects/<project>.")

        mcp = _value("RAG_MCP_ENDPOINT")
        if deployment:
            parts = _https_url("RAG_MCP_ENDPOINT", mcp)
            if not re.fullmatch(r"/knowledgebases/[^/]+/mcp", parts.path):
                raise ConfigError("RAG_MCP_ENDPOINT must use /knowledgebases/<name>/mcp.")
            query = parse_qs(parts.query, keep_blank_values=True)
            if set(query) != {"api-version"} or len(query["api-version"]) != 1:
                raise ConfigError("RAG_MCP_ENDPOINT must have only one api-version parameter.")
            if not re.fullmatch(r"\d{4}-\d{2}-\d{2}(?:-preview)?", query["api-version"][0]):
                raise ConfigError("RAG_MCP_ENDPOINT requires a dated api-version.")

        name = _value("AGENT_NAME", "RagAgent")
        if not re.fullmatch(r"[A-Za-z0-9](?:[A-Za-z0-9-]{0,61}[A-Za-z0-9])?", name):
            raise ConfigError("AGENT_NAME must use 1–63 letters, digits or internal hyphens.")
        version = _value("AGENT_VERSION")
        if version and not re.fullmatch(r"[1-9]\d*", version):
            raise ConfigError("AGENT_VERSION must be an explicit positive version number.")
        model = _value("MODEL_DEPLOYMENT", "gpt-4.1-mini")
        if not model:
            raise ConfigError("MODEL_DEPLOYMENT cannot be empty.")
        mode = _value("AZURE_CREDENTIAL_MODE", "default")
        if mode not in {"default", "managed_identity", "cli"}:
            raise ConfigError("AZURE_CREDENTIAL_MODE must be default, managed_identity or cli.")
        return cls(
            project_endpoint=endpoint,
            agent_name=name,
            agent_version=version,
            model_deployment=model,
            rag_mcp_endpoint=mcp,
            project_connection_name=_value("PROJECT_CONNECTION_NAME"),
            credential_mode=mode,
            managed_identity_client_id=_value("MANAGED_IDENTITY_CLIENT_ID"),
            timeout_seconds=_integer("REQUEST_TIMEOUT_SECONDS", 120, 10, 600),
            max_output_tokens=_integer("MAX_OUTPUT_TOKENS", 2048, 256, 16384),
            max_question_chars=_integer("MAX_QUESTION_CHARS", 8000, 1, 32000),
            history_turns=_integer("HISTORY_TURNS", 6, 0, 20),
            deployment_file=Path(_value("DEPLOYMENT_FILE", "deployment.json")),
        )
