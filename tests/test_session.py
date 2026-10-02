import json
from dataclasses import replace
from unittest.mock import Mock

import httpx
import pytest
from openai import APIConnectionError, OpenAI

from rag_foundry.config import ConfigError
from rag_foundry.grounding import GroundingError
from rag_foundry.session import RagSession
from tests.conftest import response_payload


def test_real_sdk_serializes_pinned_agent_and_guarded_answer(settings):
    requests = []

    def respond(request):
        requests.append(json.loads(request.content))
        assert request.url.path == "/api/projects/test/openai/v1/responses"
        return httpx.Response(200, json=response_payload())

    transport = httpx.MockTransport(respond)
    with (
        httpx.Client(transport=transport, trust_env=False) as http_client,
        OpenAI(
            api_key="test",
            base_url=settings.project_endpoint + "/openai/v1",
            http_client=http_client,
        ) as client,
    ):
        answer = RagSession(client, settings, "2").ask("What is the policy?")
    assert answer.sources[0]["ref_id"] == "0"
    assert requests[0]["agent_reference"]["version"] == "2"
    assert requests[0]["store"] is False
    assert requests[0]["tool_choice"] == {
        "type": "mcp",
        "server_label": "KnowledgeBase",
        "name": "knowledge_base_retrieve",
    }


def test_rejected_answer_never_enters_history(settings):
    client = Mock()
    client.responses.create.side_effect = [
        response_payload(),
        response_payload("Unverified secret"),
        response_payload(),
    ]
    session = RagSession(client, settings, "2")
    session.ask("First")
    with pytest.raises(GroundingError):
        session.ask("Rejected query")
    session.ask("Third")
    sent = client.responses.create.call_args.kwargs["input"]
    assert [item["content"] for item in sent] == ["First", "Policy is 30 days. [ref_id:0]", "Third"]


def test_network_failure_does_not_change_history(settings):
    client = Mock()
    client.responses.create.side_effect = APIConnectionError(
        request=httpx.Request("POST", "https://example.com")
    )
    session = RagSession(client, settings, "2")
    with pytest.raises(APIConnectionError):
        session.ask("Question")
    assert session.history == []


@pytest.mark.parametrize("turns", [0, 1, 3])
def test_history_is_bounded(settings, turns):
    client = Mock()
    client.responses.create.return_value = response_payload()
    session = RagSession(client, replace(settings, history_turns=turns), "2")
    for index in range(8):
        session.ask(f"Question {index}")
    assert len(session.history) == turns * 2


@pytest.mark.parametrize("question", ["", " ", "x" * 8001])
def test_invalid_question_is_rejected_before_api_request(settings, question):
    client = Mock()
    with pytest.raises(ConfigError):
        RagSession(client, settings, "2").ask(question)
    client.responses.create.assert_not_called()
