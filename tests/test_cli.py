import sys
from contextlib import nullcontext
from unittest.mock import Mock

import pytest
from azure.core.exceptions import HttpResponseError

import chat
import delete_rag_agent
import smoke_test
from rag_foundry.errors import report_error, run
from tests.conftest import response_payload


@pytest.mark.parametrize(
    "args", [[], ["--yes"], ["--all"], ["--version", "1"], ["--version", "latest", "--yes"]]
)
def test_delete_requires_explicit_target_and_confirmation(monkeypatch, args):
    project = Mock()
    monkeypatch.setattr(delete_rag_agent, "project_client", project)
    monkeypatch.setattr(sys, "argv", ["delete_rag_agent.py", *args])
    with pytest.raises(SystemExit) as exc:
        delete_rag_agent.main()
    assert exc.value.code == 2
    project.assert_not_called()


def test_errors_do_not_print_remote_body(capsys):
    report_error(HttpResponseError(message="token=TOP_SECRET document=PRIVATE"))
    captured = capsys.readouterr()
    assert "TOP_SECRET" not in captured.err
    assert "PRIVATE" not in captured.err
    assert "HttpResponseError" in captured.err


def test_cli_failure_exit_code():
    def fail():
        raise HttpResponseError(message="private")

    assert run(fail) == 1


def test_delete_uses_explicit_version(settings, monkeypatch):
    project = Mock()
    monkeypatch.setattr(delete_rag_agent, "project_client", lambda cfg: nullcontext(project))
    monkeypatch.setattr(sys, "argv", ["delete_rag_agent.py", "--version", "7", "--yes"])
    assert delete_rag_agent.main() == 0
    project.agents.delete_version.assert_called_once_with(
        agent_name=settings.agent_name, agent_version="7"
    )
    project.agents.delete.assert_not_called()


def test_one_shot_cli_does_not_emit_rejected_answer(settings, monkeypatch, capsys):
    project, client = Mock(), Mock()
    client.responses.create.return_value = response_payload("PRIVATE_UNGROUNDED_ANSWER")
    monkeypatch.setattr(chat, "project_client", lambda cfg: nullcontext(project))
    monkeypatch.setattr(chat, "responses_client", lambda *args: nullcontext(client))
    monkeypatch.setattr(sys, "argv", ["chat.py", "--version", "2", "--question", "Test", "--json"])
    assert run(chat.main) == 1
    captured = capsys.readouterr()
    assert captured.out == ""
    assert "PRIVATE_UNGROUNDED_ANSWER" not in captured.err


@pytest.mark.parametrize(
    "known,unknown,exit_code",
    [
        ("30 days [ref_id:0]", "I don't know", 0),
        ("90 days [ref_id:0]", "I don't know", 1),
        ("30 days [ref_id:0]", "Unsupported answer [ref_id:0]", 1),
        ("30 days [ref_id:0]", "I don't know, probably something", 1),
    ],
)
def test_live_smoke_command_contract(settings, monkeypatch, known, unknown, exit_code):
    project, client = Mock(), Mock()
    client.responses.create.side_effect = [response_payload(known), response_payload(unknown)]
    monkeypatch.setattr(smoke_test, "project_client", lambda cfg: nullcontext(project))
    monkeypatch.setattr(smoke_test, "responses_client", lambda *args: nullcontext(client))
    monkeypatch.setattr(
        sys,
        "argv",
        [
            "smoke_test.py",
            "--version",
            "2",
            "--known-question",
            "Known",
            "--expected-substring",
            "30 days",
            "--unknown-question",
            "Unknown",
        ],
    )
    assert run(smoke_test.main) == exit_code
