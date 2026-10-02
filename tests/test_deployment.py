import json
from types import SimpleNamespace
from unittest.mock import Mock

import pytest
from azure.core.exceptions import HttpResponseError, ResourceNotFoundError

from rag_foundry.agent import definition, deploy
from rag_foundry.config import ConfigError
from rag_foundry.deployment import resolve_version, write_manifest


def agent(settings, version="2"):
    return SimpleNamespace(
        name=settings.agent_name, version=version, definition=definition(settings)
    )


def test_unchanged_definition_does_not_create_version(settings):
    project = Mock()
    current = agent(settings)
    project.agents.get.return_value.versions.latest = current
    selected, created, digest = deploy(project, settings)
    assert selected is current
    assert not created
    assert len(digest) == 64
    project.agents.create_version.assert_not_called()


def test_missing_agent_creates_first_version(settings):
    project = Mock()
    project.agents.get.side_effect = ResourceNotFoundError()
    project.agents.create_version.return_value = agent(settings, "1")
    selected, created, digest = deploy(project, settings)
    assert created and selected.version == "1"
    assert project.agents.create_version.call_args.kwargs["metadata"]["config_sha256"] == digest


def test_changed_definition_creates_new_version(settings):
    project = Mock()
    current = agent(settings)
    current.definition.model = "previous-model"
    project.agents.get.return_value.versions.latest = current
    project.agents.create_version.return_value = agent(settings, "3")
    assert deploy(project, settings)[1]


def test_force_creates_new_version(settings):
    project = Mock()
    project.agents.get.return_value.versions.latest = agent(settings)
    project.agents.create_version.return_value = agent(settings, "3")
    assert deploy(project, settings, force=True)[1]


def test_permission_error_does_not_create_agent(settings):
    project = Mock()
    project.agents.get.side_effect = HttpResponseError(message="Access denied")
    with pytest.raises(HttpResponseError):
        deploy(project, settings)
    project.agents.create_version.assert_not_called()


def test_manifest_round_trip_and_atomic_replacement(settings):
    path = settings.deployment_file
    write_manifest(path, settings, agent(settings), "digest")
    assert resolve_version(settings) == "2"
    write_manifest(path, settings, agent(settings, "3"), "digest")
    assert resolve_version(settings) == "3"
    assert list(path.parent.glob("tmp*")) == []


def test_version_override_for_rollback(settings):
    assert resolve_version(settings, "1") == "1"


@pytest.mark.parametrize(
    "data",
    [
        [],
        {"schema_version": 2},
        {
            "schema_version": 1,
            "project_endpoint": "another",
            "agent_name": "RagAgent",
            "agent_version": "2",
        },
        {
            "schema_version": 1,
            "project_endpoint": "https://example.services.ai.azure.com/api/projects/test",
            "agent_name": "RagAgent",
            "agent_version": "latest",
        },
    ],
)
def test_wrong_manifest_rejected(settings, data):
    settings.deployment_file.write_text(json.dumps(data), encoding="utf-8")
    with pytest.raises(ConfigError):
        resolve_version(settings)


def test_missing_manifest_requires_pin(settings):
    with pytest.raises(ConfigError, match="Pin AGENT_VERSION"):
        resolve_version(settings)


def test_invalid_json_manifest(settings):
    settings.deployment_file.write_text("{", encoding="utf-8")
    with pytest.raises(ConfigError, match="valid UTF-8 JSON"):
        resolve_version(settings)
