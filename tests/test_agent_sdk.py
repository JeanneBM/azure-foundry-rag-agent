"""Exercise actual Azure SDK serialization and deserialization without Azure."""

import json

import pytest
from azure.ai.projects import AIProjectClient
from azure.core.credentials import AccessToken
from azure.core.exceptions import ServiceRequestError
from azure.core.pipeline.transport import HttpResponse, HttpTransport

from rag_foundry.agent import definition, deploy


class TestCredential:
    __test__ = False

    def get_token(self, *scopes, **kwargs):
        return AccessToken("offline-test-token", 9999999999)


class JsonResponse(HttpResponse):
    def __init__(self, request, status, data):
        super().__init__(request, None)
        self.status_code = status
        self.headers = {"content-type": "application/json"}
        self.content_type = "application/json"
        self.reason = "test response"
        self._body = json.dumps(data).encode()

    def body(self):
        return self._body

    def text(self, encoding=None):
        return self._body.decode(encoding or "utf-8")

    def json(self):
        return json.loads(self._body)


class AgentTransport(HttpTransport):
    def __init__(self, settings, *, fail_create=False, existing=False):
        self.settings = settings
        self.fail_create = fail_create
        self.existing = existing
        self.requests = []

    def open(self):
        pass

    def close(self):
        pass

    def __enter__(self):
        return self

    def __exit__(self, *args):
        self.close()

    def send(self, request, **kwargs):
        self.requests.append(request)
        if request.method == "GET":
            if self.existing:
                return JsonResponse(
                    request,
                    200,
                    {
                        "object": "agent",
                        "id": "agent_test",
                        "name": self.settings.agent_name,
                        "versions": {
                            "latest": {
                                "object": "agent.version",
                                "id": "agent_version_test",
                                "name": self.settings.agent_name,
                                "version": "2",
                                "created_at": 1,
                                "metadata": {},
                                "definition": definition(self.settings).as_dict(),
                            }
                        },
                    },
                )
            return JsonResponse(request, 404, {"error": {"code": "NotFound", "message": "test"}})
        if self.fail_create:
            raise ServiceRequestError("Simulated lost create response")
        payload = json.loads(request.body)
        return JsonResponse(
            request,
            200,
            {
                "object": "agent.version",
                "id": "agent_test",
                "name": self.settings.agent_name,
                "version": "1",
                "created_at": 1,
                "metadata": payload["metadata"],
                "definition": payload["definition"],
            },
        )


def test_azure_sdk_deploy_contract(settings):
    transport = AgentTransport(settings)
    with AIProjectClient(
        settings.project_endpoint, TestCredential(), transport=transport, retry_total=0
    ) as project:
        agent, created, digest = deploy(project, settings)
    assert created and agent.version == "1"
    assert agent.definition.as_dict() == definition(settings).as_dict()
    assert agent.metadata["config_sha256"] == digest
    request = transport.requests[-1]
    assert request.method == "POST"
    body = json.loads(request.body)
    assert body["definition"]["tool_choice"] == {
        "type": "mcp",
        "server_label": "KnowledgeBase",
        "name": "knowledge_base_retrieve",
    }
    tool = body["definition"]["tools"][0]
    assert tool["project_connection_id"] == settings.project_connection_name
    assert tool["allowed_tools"] == ["knowledge_base_retrieve"]


def test_azure_create_is_not_retried_after_connection_loss(settings):
    transport = AgentTransport(settings, fail_create=True)
    with (
        AIProjectClient(
            settings.project_endpoint, TestCredential(), transport=transport, retry_total=0
        ) as project,
        pytest.raises(ServiceRequestError),
    ):
        deploy(project, settings)
    assert sum(request.method == "POST" for request in transport.requests) == 1


def test_azure_sdk_reuses_deserialized_latest_version(settings):
    transport = AgentTransport(settings, existing=True)
    with AIProjectClient(
        settings.project_endpoint, TestCredential(), transport=transport, retry_total=0
    ) as project:
        agent, created, _ = deploy(project, settings)
    assert agent.version == "2" and not created
    assert len(transport.requests) == 1
