"""Native URL citations must resolve to actual evidence, never arbitrary links."""

import pytest
from openai.types.responses import Response

from rag_foundry.grounding import GroundingError, validate_response
from tests.conftest import response_payload

URL = "https://example.search.windows.net/indexes/demo-docs/docs/returns?api-version=2026-08-01-preview"


def native_payload():
    payload = response_payload(
        "The return period is 30 days. [1]",
        [{"ref_id": "document-1", "content": "Return within 30 days.", "url": URL}],
    )
    payload["output"][1]["content"][0]["annotations"] = [
        {"type": "url_citation", "start_index": 29, "end_index": 32, "url": URL, "title": "Returns"}
    ]
    return payload


def test_real_sdk_native_citation_accepts_exact_retrieved_url():
    answer = validate_response(Response.model_validate(native_payload()))
    assert answer.sources == ({"ref_id": "document-1", "url": URL},)
    assert not answer.unknown


def test_native_citation_without_retrieval_is_rejected():
    payload = native_payload()
    payload["output"].pop(0)
    with pytest.raises(GroundingError, match="missing_retrieval_call"):
        validate_response(payload)


@pytest.mark.parametrize("url", ["https://invented.example/doc", URL + "&changed=true"])
def test_native_url_must_match_evidence_verbatim(url):
    payload = native_payload()
    payload["output"][1]["content"][0]["annotations"][0]["url"] = url
    with pytest.raises(GroundingError, match="unknown_citation"):
        validate_response(payload)


@pytest.mark.parametrize(
    "change",
    [
        {"start_index": -1},
        {"end_index": 10000},
        {"start_index": True},
        {"end_index": 0},
        {"url": None},
        {"url": ""},
    ],
)
def test_malformed_native_citation_is_rejected(change):
    payload = native_payload()
    payload["output"][1]["content"][0]["annotations"][0].update(change)
    with pytest.raises(GroundingError, match="malformed_citation"):
        validate_response(payload)


def test_ambiguous_native_url_is_rejected():
    payload = native_payload()
    import json

    payload["output"][0]["output"] = json.dumps(
        [
            {"ref_id": "1", "content": "First chunk", "url": URL},
            {"ref_id": "2", "content": "Second chunk", "url": URL},
        ]
    )
    with pytest.raises(GroundingError, match="ambiguous_citation_url"):
        validate_response(payload)


def test_invented_inline_id_is_not_rescued_by_valid_native_citation():
    payload = native_payload()
    payload["output"][1]["content"][0]["text"] += " [ref_id:invented]"
    with pytest.raises(GroundingError, match="unknown_citation"):
        validate_response(payload)
