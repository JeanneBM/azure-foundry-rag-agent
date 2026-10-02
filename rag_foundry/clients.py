"""Entra authentication and deterministic client cleanup."""

from contextlib import ExitStack, contextmanager

from azure.ai.projects import AIProjectClient
from azure.identity import AzureCliCredential, DefaultAzureCredential, ManagedIdentityCredential

from rag_foundry.config import Settings


def make_credential(settings: Settings):
    if settings.credential_mode == "managed_identity":
        kwargs = {}
        if settings.managed_identity_client_id:
            kwargs["client_id"] = settings.managed_identity_client_id
        return ManagedIdentityCredential(**kwargs)
    if settings.credential_mode == "cli":
        return AzureCliCredential(process_timeout=30)
    return DefaultAzureCredential(exclude_interactive_browser_credential=True)


@contextmanager
def project_client(settings: Settings):
    with ExitStack() as stack:
        credential = make_credential(settings)
        stack.callback(credential.close)
        project = AIProjectClient(
            endpoint=settings.project_endpoint,
            credential=credential,
            connection_timeout=30,
            read_timeout=settings.timeout_seconds,
            # A create_version retry after a lost response can create duplicate versions.
            retry_total=0,
        )
        stack.callback(project.close)
        yield project


@contextmanager
def responses_client(project, settings: Settings):
    with project.get_openai_client(
        timeout=float(settings.timeout_seconds), max_retries=2
    ) as client:
        yield client
