"""CLI failures without leaking Azure error bodies or document contents."""

import sys

from azure.core.exceptions import AzureError, ClientAuthenticationError
from openai import APIConnectionError, APIError, APITimeoutError

from rag_foundry.config import ConfigError
from rag_foundry.grounding import GroundingError


def report_error(exc: Exception) -> None:
    if isinstance(exc, ConfigError):
        message = str(exc)
    elif isinstance(exc, GroundingError):
        message = f"Answer rejected by grounding checks ({exc})."
    elif isinstance(exc, ClientAuthenticationError):
        message = "Azure authentication failed. Check login, identity and role assignments."
    elif isinstance(exc, (APIConnectionError, APITimeoutError)):
        message = "Azure request timed out or could not connect. Check network access."
    elif isinstance(exc, (AzureError, APIError)):
        status = getattr(exc, "status_code", None)
        message = f"Azure request failed ({type(exc).__name__}, status={status})."
    else:
        message = f"Operation failed ({type(exc).__name__}). Check configuration and file access."
    print(message, file=sys.stderr)


def run(command) -> int:
    try:
        return command()
    except (ConfigError, GroundingError, AzureError, APIError, OSError) as exc:
        report_error(exc)
        return 1
    except KeyboardInterrupt:
        print("Interrupted.", file=sys.stderr)
        return 130
