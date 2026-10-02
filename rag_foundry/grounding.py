"""Fail-closed validation of MCP retrieval evidence and answer citations.

These checks establish provenance, not semantic entailment of every claim.
Unknown tool output formats are rejected rather than guessed.
"""

from __future__ import annotations

import json
import re
from dataclasses import dataclass
from typing import Any

from rag_foundry.agent import RETRIEVE_TOOL, SERVER_LABEL, UNKNOWN_ANSWER

CITATION = re.compile(r"\[ref_id:([A-Za-z0-9_.-]+)\]")
REFERENCE_ID = re.compile(r"[A-Za-z0-9_.-]+")
MAX_TOOL_OUTPUT_CHARS = 2_000_000


class GroundingError(ValueError):
    """A safe diagnostic that contains no user query or retrieved content."""


@dataclass(frozen=True)
class Answer:
    text: str
    sources: tuple[dict[str, Any], ...]
    response_id: str
    unknown: bool


def _decode(payload: Any, depth: int = 0) -> list[dict[str, Any]]:
    if depth > 8:
        raise GroundingError("unsupported_retrieval_format")
    if isinstance(payload, str):
        if len(payload) > MAX_TOOL_OUTPUT_CHARS:
            raise GroundingError("retrieval_output_too_large")
        try:
            decoded = json.loads(payload)
        except (ValueError, RecursionError) as exc:
            raise GroundingError("unsupported_retrieval_format") from exc
        return _decode(decoded, depth + 1)
    if isinstance(payload, dict):
        if payload.get("isError"):
            raise GroundingError("retrieval_failed")
        if "result" in payload:
            return _decode(payload["result"], depth + 1)
        if isinstance(payload.get("content"), list):
            return _decode(payload["content"], depth + 1)
        if payload.get("type") == "text" and isinstance(payload.get("text"), str):
            return _decode(payload["text"], depth + 1)
        if "ref_id" in payload and isinstance(payload.get("content"), str):
            ref_id = payload["ref_id"]
            if isinstance(ref_id, int) and not isinstance(ref_id, bool):
                ref_id = str(ref_id)
            if (
                not isinstance(ref_id, str)
                or not REFERENCE_ID.fullmatch(ref_id)
                or not payload["content"].strip()
            ):
                raise GroundingError("invalid_grounding_record")
            return [{**payload, "ref_id": ref_id}]
    if isinstance(payload, list):
        records = []
        for item in payload:
            records.extend(_decode(item, depth + 1))
        return records
    raise GroundingError("unsupported_retrieval_format")


def validate_response(response) -> Answer:
    data = response if isinstance(response, dict) else response.model_dump(mode="json")
    if data.get("status") != "completed" or data.get("error") or data.get("incomplete_details"):
        raise GroundingError("response_not_completed")
    records: dict[str, dict[str, Any]] = {}
    retrieved = False
    texts = []
    for item in data.get("output", []):
        kind = item.get("type")
        if kind == "mcp_approval_request":
            raise GroundingError("unexpected_approval_request")
        if kind == "mcp_call":
            if item.get("server_label") != SERVER_LABEL or item.get("name") != RETRIEVE_TOOL:
                raise GroundingError("unexpected_tool_call")
            if item.get("error") or item.get("status") not in (None, "completed"):
                raise GroundingError("retrieval_failed")
            output = item.get("output")
            if output is None:
                raise GroundingError("missing_retrieval_output")
            extracted = _decode(output)
            retrieved = True
            for record in extracted:
                key = record["ref_id"]
                if key in records and records[key] != record:
                    raise GroundingError("ambiguous_reference_id")
                records[key] = record
        elif kind == "message" and item.get("role") == "assistant":
            if item.get("status") not in (None, "completed"):
                raise GroundingError("message_not_completed")
            for content in item.get("content", []):
                if content.get("type") == "refusal":
                    raise GroundingError("model_refusal")
                if content.get("type") == "output_text":
                    texts.append(content.get("text", ""))
        elif kind not in {"reasoning", "mcp_list_tools"}:
            raise GroundingError("unexpected_output_item")

    if not retrieved:
        raise GroundingError("missing_retrieval_call")
    text = "\n".join(texts).strip()
    if not text:
        raise GroundingError("empty_answer")
    if text == UNKNOWN_ANSWER:
        return Answer(text, (), str(data.get("id", "")), True)
    cited = list(dict.fromkeys(CITATION.findall(text)))
    if not cited:
        raise GroundingError("missing_citations")
    if "[ref_id:" in CITATION.sub("", text):
        raise GroundingError("malformed_citation")
    if any(key not in records for key in cited):
        raise GroundingError("unknown_citation")
    # Metadata only: don't repeat full retrieved chunks in the UI or logs.
    sources = tuple(
        {key: value for key, value in records[ref].items() if key != "content"} for ref in cited
    )
    return Answer(text, sources, str(data.get("id", "")), False)
