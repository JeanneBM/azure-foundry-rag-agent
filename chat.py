"""Interactive or one-shot chat with a pinned Foundry RAG agent version."""

import argparse
import json
import sys

from azure.core.exceptions import AzureError
from openai import APIError

from rag_foundry.clients import project_client, responses_client
from rag_foundry.config import ConfigError, Settings
from rag_foundry.deployment import resolve_version
from rag_foundry.errors import report_error, run
from rag_foundry.grounding import GroundingError
from rag_foundry.session import RagSession


def print_answer(answer, *, as_json: bool = False) -> None:
    if as_json:
        print(
            json.dumps(
                {
                    "answer": answer.text,
                    "sources": answer.sources,
                    "response_id": answer.response_id,
                    "unknown": answer.unknown,
                },
                ensure_ascii=False,
            )
        )
        return
    print(f"\nAgent: {answer.text}\n")
    if answer.sources:
        print("Sources:")
        for source in answer.sources:
            print(json.dumps(source, ensure_ascii=False))
        print()


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--version", help="Explicit agent version; overrides AGENT_VERSION")
    parser.add_argument("--question", help="Ask once and exit (suitable for smoke checks)")
    parser.add_argument("--json", action="store_true", help="JSON output for --question")
    args = parser.parse_args()
    if args.json and args.question is None:
        parser.error("--json requires --question")
    settings = Settings.from_env()
    version = resolve_version(settings, args.version)
    with project_client(settings) as project:
        project.agents.get_version(settings.agent_name, version)
        with responses_client(project, settings) as client:
            session = RagSession(client, settings, version)
            if args.question is not None:
                print_answer(session.ask(args.question), as_json=args.json)
                return 0
            print(f"Agent: {settings.agent_name}, version {version}. Type exit to quit.")
            while True:
                try:
                    question = input("You: ").strip()
                except (EOFError, KeyboardInterrupt):
                    print("\nBye!")
                    return 0
                if question.lower() in {"exit", "quit", "q"}:
                    return 0
                if not question:
                    continue
                try:
                    print_answer(session.ask(question))
                except GroundingError as exc:
                    print("\nAgent: I don't know\n")
                    report_error(exc)
                except (ConfigError, AzureError, APIError) as exc:
                    report_error(exc)
                    print("Request failed. You can retry or exit.", file=sys.stderr)


if __name__ == "__main__":
    raise SystemExit(run(main))
