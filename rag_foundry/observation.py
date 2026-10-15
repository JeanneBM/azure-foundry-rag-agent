"""Observe returned MCP records and citations independently of answer acceptance."""

from rag_foundry.agent import UNKNOWN_ANSWER
from rag_foundry.grounding import CITATION, GroundingError, _decode


def observe_response(response, trace):
    data = response if isinstance(response, dict) else response.model_dump(mode="json")
    usage = data.get("usage") or {}
    trace.event(
        "llm_call",
        tokens=usage.get("total_tokens", 0),
        attrs={"usage_available": "total_tokens" in usage},
    )
    retrieved = set()
    texts = []
    for item in data.get("output", []):
        if item.get("type") == "mcp_call":
            # Tool names are observed, never replaced with the expected allowlisted name.
            trace.tool(item.get("name") or "unknown_mcp_tool", item.get("arguments"))
            if not item.get("error"):
                try:
                    retrieved.update(record["ref_id"] for record in _decode(item.get("output")))
                except GroundingError:
                    trace.event("escalation", status="invalid_retrieval_metadata")
        if item.get("type") == "message" and item.get("role") == "assistant":
            texts.extend(
                part.get("text", "")
                for part in item.get("content", [])
                if part.get("type") == "output_text"
            )
    text = "\n".join(texts).strip()
    trace.event(
        "answer",
        citations=list(dict.fromkeys(CITATION.findall(text))),
        retrieved=sorted(retrieved),
        status="abstained" if text == UNKNOWN_ANSWER else "answered",
    )
