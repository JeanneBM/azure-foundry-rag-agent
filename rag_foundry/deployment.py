"""Local release manifest: pins clients to a tested immutable agent version."""

import json
import os
import re
import tempfile
from pathlib import Path

from rag_foundry.config import ConfigError, Settings


def write_manifest(path: Path, settings: Settings, agent, digest: str) -> None:
    data = {
        "schema_version": 1,
        "project_endpoint": settings.project_endpoint,
        "agent_name": agent.name,
        "agent_version": agent.version,
        "config_sha256": digest,
    }
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = None
    try:
        with tempfile.NamedTemporaryFile(
            mode="w", encoding="utf-8", dir=path.parent, delete=False
        ) as handle:
            temporary = Path(handle.name)
            json.dump(data, handle, indent=2)
            handle.write("\n")
            handle.flush()
            os.fsync(handle.fileno())
        os.replace(temporary, path)
    finally:
        if temporary is not None:
            temporary.unlink(missing_ok=True)


def resolve_version(settings: Settings, override: str | None = None) -> str:
    version = override or settings.agent_version
    if not version:
        try:
            data = json.loads(settings.deployment_file.read_text(encoding="utf-8"))
        except FileNotFoundError as exc:
            raise ConfigError(
                "Pin AGENT_VERSION, pass --version, or create a deployment manifest first."
            ) from exc
        except (ValueError, UnicodeError) as exc:
            raise ConfigError("Deployment manifest is not valid UTF-8 JSON.") from exc
        if not isinstance(data, dict) or data.get("schema_version") != 1:
            raise ConfigError("Unsupported deployment manifest format.")
        if (
            data.get("project_endpoint") != settings.project_endpoint
            or data.get("agent_name") != settings.agent_name
        ):
            raise ConfigError("Deployment manifest belongs to another project or agent.")
        version = data.get("agent_version")
    if not isinstance(version, str) or not re.fullmatch(r"[1-9]\d*", version):
        raise ConfigError("Agent version must be an explicit positive version number.")
    return version
