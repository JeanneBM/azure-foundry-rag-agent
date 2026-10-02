"""Create or reuse an immutable agent version and write its release manifest."""

import argparse

from rag_foundry.agent import deploy
from rag_foundry.clients import project_client
from rag_foundry.config import Settings
from rag_foundry.deployment import write_manifest
from rag_foundry.errors import run


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--force", action="store_true", help="Create a new version even if unchanged"
    )
    args = parser.parse_args()
    settings = Settings.from_env(deployment=True)
    with project_client(settings) as project:
        agent, created, digest = deploy(project, settings, force=args.force)
    write_manifest(settings.deployment_file, settings, agent, digest)
    action = "Created" if created else "Reused"
    print(f"{action} {agent.name}, version {agent.version}.")
    print(f"Manifest: {settings.deployment_file}")
    print(f"Pin AGENT_VERSION={agent.version} in your client environment.")
    return 0


if __name__ == "__main__":
    raise SystemExit(run(main))
