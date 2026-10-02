"""Bounded local history containing only accepted answers."""

from rag_foundry.agent import RETRIEVE_TOOL, SERVER_LABEL
from rag_foundry.config import ConfigError, Settings
from rag_foundry.grounding import validate_response


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
        user = {"role": "user", "content": question}
        response = self.client.responses.create(
            input=[*self.history, user],
            store=False,
            max_output_tokens=self.settings.max_output_tokens,
            tool_choice={"type": "mcp", "server_label": SERVER_LABEL, "name": RETRIEVE_TOOL},
            extra_body={
                "agent_reference": {
                    "name": self.settings.agent_name,
                    "version": self.version,
                    "type": "agent_reference",
                }
            },
        )
        answer = validate_response(response)
        self.history.extend([user, {"role": "assistant", "content": answer.text}])
        limit = self.settings.history_turns * 2
        self.history = self.history[-limit:] if limit else []
        return answer
