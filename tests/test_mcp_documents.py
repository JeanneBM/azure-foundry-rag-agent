"""Regression for the documents/id envelope observed in the live demo MCP output."""

import json

import pytest

from rag_foundry.grounding import GroundingError, validate_response
from tests.conftest import response_payload

DOCUMENT_ID = "78be819e-baf7-488c-8925-c670a8179d91"
URL = "https://example.search.windows.net/indexes/demo-docs/docs/returns?$select=title%2Ccontent%2Cid&api-version=2026-08-01-preview&allowUnsafeKeys=true"


def document():
    return {
        "id": DOCUMENT_ID,
        "content": json.dumps(
            {
                "id": "returns",
                "title": "Demo return policy",
                "content": (
                    "The product return period is 30 days after delivery. "
                    "This policy is synthetic demo data."
                ),
            },
            indent=2,
        ).replace("\n", "\r\n"),
        "title": URL,
        "url": URL,
        "metadata": "application/json",
        "knowledgeSourceIndex": 0,
    }


def payload(documents, text=None):
    response = response_payload(text or f"Return within 30 days. [ref_id:{DOCUMENT_ID}]")
    response["output"][0]["output"] = json.dumps({"documents": documents})
    return response


@pytest.mark.parametrize("envelope", ["direct", "double_json", "mcp_content"])
def test_live_documents_envelope_preserves_actual_id_and_url(envelope):
    response = payload([document()])
    if envelope == "double_json":
        response["output"][0]["output"] = json.dumps(response["output"][0]["output"])
    elif envelope == "mcp_content":
        response["output"][0]["output"] = json.dumps(
            {
                "result": {"content": [{"type": "text", "text": response["output"][0]["output"]}]},
            }
        )
    answer = validate_response(response)
    assert answer.sources == (
        {
            "ref_id": DOCUMENT_ID,
            "id": DOCUMENT_ID,
            "title": URL,
            "url": URL,
            "knowledgeSourceIndex": 0,
        },
    )
    assert not answer.unknown
    assert "content" not in answer.sources[0]


@pytest.mark.parametrize("citation", ["0", "returns", "invented"])
def test_documents_do_not_authorize_positional_or_embedded_ids(citation):
    with pytest.raises(GroundingError, match="unknown_citation"):
        validate_response(payload([document()], f"30 days [ref_id:{citation}]"))


def test_empty_documents_allow_only_fixed_unknown():
    assert validate_response(payload([], "I don't know")).unknown
    with pytest.raises(GroundingError, match="unknown_citation"):
        validate_response(payload([]))


@pytest.mark.parametrize(
    "documents",
    [
        None,
        {},
        [None],
        [{"content": "text"}],
        [{"id": "x", "content": ""}],
        [{"id": "x", "content": 42}],
        [{"id": "bad id", "content": "text"}],
    ],
)
def test_malformed_documents_fail_closed(documents):
    with pytest.raises(GroundingError, match="invalid_grounding_record"):
        validate_response(payload(documents))


def test_conflicting_outer_ids_rejected():
    first = document()
    second = {**first, "content": "Different content"}
    with pytest.raises(GroundingError, match="ambiguous_reference_id"):
        validate_response(payload([first, second]))
