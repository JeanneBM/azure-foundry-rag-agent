import json
from unittest.mock import Mock

import pytest

from rag_foundry.grounding import GroundingError
from rag_foundry.session import RagSession
from tests.conftest import response_payload


def test_rejected_answer_is_observed_before_gate(settings, tmp_path, monkeypatch):
    path = tmp_path / "events"
    monkeypatch.setenv("AGENT_TELEMETRY_FILE", str(path))
    client = Mock()
    client.responses.create.return_value = response_payload("Private answer [ref_id:99]")
    with pytest.raises(GroundingError):
        RagSession(client, settings, "2").ask("Private question")
    raw = path.read_text()
    events = [json.loads(line) for line in raw.splitlines()]
    assert "Private answer" not in raw and "Private question" not in raw
    observed = next(e for e in events if e["type"] == "answer")
    assert observed["citations"] == ["99"] and "0" in observed["retrieved"]
    assert events[-1]["status"] == "error"
