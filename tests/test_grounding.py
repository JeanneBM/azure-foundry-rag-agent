import json

import pytest
from openai.types.responses import Response

from rag_foundry.grounding import GroundingError, validate_response
from tests.conftest import response_payload


def test_accepts_actual_sdk_response_and_exposes_only_cited_sources():
    payload = response_payload(
        records=[
            {"ref_id": "0", "title": "Policy", "content": "30 days"},
            {"ref_id": "1", "title": "Uncited", "content": "Other"},
        ]
    )
    answer = validate_response(Response.model_validate(payload))
    assert answer.text == "Policy is 30 days. [ref_id:0]"
    assert answer.sources == ({"ref_id": "0", "title": "Policy"},)
    assert not answer.unknown


@pytest.mark.parametrize("wrapped", [False, True])
def test_documented_mcp_content_envelope(wrapped):
    payload = response_payload()
    output = {"content": [{"type": "text", "text": payload["output"][0]["output"]}]}
    if wrapped:
        output = {"result": output}
    payload["output"][0]["output"] = json.dumps(output)
    assert validate_response(payload).sources[0]["ref_id"] == "0"


def test_empty_retrieval_can_only_produce_exact_unknown():
    assert validate_response(response_payload("I don't know", [])).unknown
    with pytest.raises(GroundingError, match="unknown_citation"):
        validate_response(response_payload(records=[]))


@pytest.mark.parametrize(
    "text,reason",
    [
        ("Ungrounded answer", "missing_citations"),
        ("Policy [ref_id:99]", "unknown_citation"),
        ("Policy [ref_id:0] and [ref_id:invalid id]", "malformed_citation"),
        ("I don't know, but probably 30 days.", "missing_citations"),
        ("", "empty_answer"),
    ],
)
def test_rejects_unverifiable_answers(text, reason):
    with pytest.raises(GroundingError, match=reason):
        validate_response(response_payload(text))


@pytest.mark.parametrize("status", ["incomplete", "failed", "in_progress"])
def test_rejects_partial_response(status):
    payload = response_payload()
    payload["status"] = status
    with pytest.raises(GroundingError, match="response_not_completed"):
        validate_response(payload)


@pytest.mark.parametrize(
    "changes,reason",
    [
        ({"error": {"message": "secret"}}, "retrieval_failed"),
        ({"status": "failed"}, "retrieval_failed"),
        ({"output": None}, "missing_retrieval_output"),
        ({"output": "not json"}, "unsupported_retrieval_format"),
        ({"output": '{"isError": true, "content": []}'}, "retrieval_failed"),
        ({"server_label": "Untrusted"}, "unexpected_tool_call"),
        ({"name": "write_document"}, "unexpected_tool_call"),
        ({"output": '[{"ref_id": "0", "content": ""}]'}, "invalid_grounding_record"),
        ({"output": '{"unexpected": []}'}, "unsupported_retrieval_format"),
    ],
)
def test_rejects_tool_failures(changes, reason):
    payload = response_payload()
    payload["output"][0].update(changes)
    with pytest.raises(GroundingError, match=reason):
        validate_response(payload)


def test_requires_new_retrieval_even_for_unknown():
    payload = response_payload("I don't know")
    payload["output"] = payload["output"][1:]
    with pytest.raises(GroundingError, match="missing_retrieval_call"):
        validate_response(payload)


def test_does_not_treat_annotations_as_retrieval_evidence():
    payload = response_payload("Fictional answer")
    payload["output"][1]["content"][0]["annotations"] = [
        {"type": "url_citation", "url": "https://example.com", "title": "Made up"}
    ]
    with pytest.raises(GroundingError, match="missing_citations"):
        validate_response(payload)


def test_conflicting_ids_rejected():
    payload = response_payload(
        records=[
            {"ref_id": "0", "content": "30 days"},
            {"ref_id": "0", "content": "90 days"},
        ]
    )
    with pytest.raises(GroundingError, match="ambiguous_reference_id"):
        validate_response(payload)


def test_approval_request_rejected():
    payload = response_payload()
    payload["output"].insert(0, {"type": "mcp_approval_request"})
    with pytest.raises(GroundingError, match="unexpected_approval_request"):
        validate_response(payload)


def test_refusal_rejected():
    payload = response_payload()
    payload["output"][1]["content"] = [{"type": "refusal", "refusal": "No"}]
    with pytest.raises(GroundingError, match="model_refusal"):
        validate_response(payload)


def test_numeric_reference_id_supported():
    payload = response_payload(records=[{"ref_id": 0, "content": "30 days"}])
    assert validate_response(payload).sources == ({"ref_id": "0"},)


def test_unexpected_tool_output_rejected():
    payload = response_payload()
    payload["output"].insert(0, {"type": "web_search_call"})
    with pytest.raises(GroundingError, match="unexpected_output_item"):
        validate_response(payload)
