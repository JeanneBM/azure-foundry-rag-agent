"""Bounded local history containing only accepted answers."""

from rag_foundry.config import ConfigError, Settings
from rag_foundry.grounding import GroundingError, validate_response
from rag_foundry.observation import observe_response
from rag_foundry.telemetry import Trace


class RagSession:
    def __init__(self, client, settings: Settings, version: str):
        self.client = client
        self.settings = settings
        self.version = version
        self.history: list[dict[str, str]] = []

    def ask(self, question: str):
        question = question.strip()
        if not question or len(question) > self.settings.max_question_chars:
            raise ConfigError(
                f"Question must contain 1–{self.settings.max_question_chars} characters."
            )
        with Trace("rag") as trace:
            return self._ask(question, trace)

    def _ask(self, question, trace):
        user = {"role": "user", "content": question}
        response = self.client.responses.create(
            input=[*self.history, user],
            store=False,
            max_output_tokens=self.settings.max_output_tokens,
            # Inherit forced retrieval from the pinned agent definition.
            # Foundry rejects conflicting per-response tool_choice overrides.
            extra_body={
                "agent_reference": {
                    "name": self.settings.agent_name,
                    "version": self.version,
                    "type": "agent_reference",
                }
            },
        )
        observe_response(response, trace)
        try:
            answer = validate_response(response)
        except GroundingError as exc:
            # Only the fixed reason code is recorded, never the response or evidence.
            trace.event("validation", status="rejected", reason=exc.code)
            raise
        trace.event("validation", status="accepted", attrs={"unknown": answer.unknown})
        self.history.extend([user, {"role": "assistant", "content": answer.text}])
        limit = self.settings.history_turns * 2
        self.history = self.history[-limit:] if limit else []
        return answer
