"""Verify a pinned release with a known KB answer and an unanswerable question."""

import argparse

from rag_foundry.clients import project_client, responses_client
from rag_foundry.config import Settings
from rag_foundry.deployment import resolve_version
from rag_foundry.errors import run
from rag_foundry.grounding import GroundingError
from rag_foundry.session import RagSession


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--version")
    parser.add_argument("--known-question", required=True)
    parser.add_argument("--expected-substring", required=True)
    parser.add_argument("--unknown-question", required=True)
    args = parser.parse_args()
    if not args.expected_substring.strip():
        parser.error("--expected-substring cannot be blank")
    settings = Settings.from_env()
    version = resolve_version(settings, args.version)
    with project_client(settings) as project:
        project.agents.get_version(settings.agent_name, version)
        with responses_client(project, settings) as client:
            known = RagSession(client, settings, version).ask(args.known_question)
            if known.unknown or args.expected_substring.casefold() not in known.text.casefold():
                raise GroundingError("known_answer_smoke_check_failed")
            unknown = RagSession(client, settings, version).ask(args.unknown_question)
            if not unknown.unknown:
                raise GroundingError("unknown_answer_smoke_check_failed")
    print(f"Smoke checks passed for {settings.agent_name}, version {version}.")
    return 0


if __name__ == "__main__":
    raise SystemExit(run(main))
