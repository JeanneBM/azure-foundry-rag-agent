"""Delete an explicitly selected version or all versions of an agent."""

import argparse
import re

from rag_foundry.clients import project_client
from rag_foundry.config import Settings
from rag_foundry.errors import run


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    target = parser.add_mutually_exclusive_group(required=True)
    target.add_argument("--version", help="Exact version to delete")
    target.add_argument("--all", action="store_true", help="Delete the entire agent")
    parser.add_argument("--yes", action="store_true", help="Confirm the destructive operation")
    args = parser.parse_args()
    if not args.yes:
        parser.error("Deletion requires --yes. Check the target agent and version first.")
    if args.version and not re.fullmatch(r"[1-9]\d*", args.version):
        parser.error("--version must be an explicit positive version number")
    settings = Settings.from_env()
    with project_client(settings) as project:
        if args.all:
            project.agents.delete(agent_name=settings.agent_name)
            print(f"Deleted agent {settings.agent_name} and all versions.")
        else:
            project.agents.delete_version(
                agent_name=settings.agent_name, agent_version=args.version
            )
            print(f"Deleted {settings.agent_name}, version {args.version}.")
    return 0


if __name__ == "__main__":
    raise SystemExit(run(main))
