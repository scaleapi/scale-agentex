import asyncio
import os
import re
from collections.abc import Mapping
from pathlib import Path

from src.adapters.authentication.exceptions import (
    AuthenticationServiceUnavailableError,
)
from src.utils.logging import make_logger

logger = make_logger(__name__)

SERVICE_ACCOUNT_TOKEN_HEADER = "X-Kubernetes-Service-Account-Token"
DEFAULT_TOKEN_PATH = "/var/run/secrets/agentex-auth/token"

_missing_token_paths_warned: set[str] = set()


async def agentex_auth_headers(
    headers: Mapping[str, str] | None = None,
) -> dict[str, str]:
    """Build headers for the configured auth provider using this pod's identity."""
    # The caller's credentials identify the user, but cannot identify this pod.
    outbound_headers = {
        name: value
        for name, value in (headers or {}).items()
        if name.lower() != SERVICE_ACCOUNT_TOKEN_HEADER.lower()
    }
    token_path = os.environ.get("AGENTEX_AUTH_SA_TOKEN_PATH", DEFAULT_TOKEN_PATH)
    try:
        # Reopen for rotation without blocking API/worker event loops on file IO.
        token = (
            await asyncio.to_thread(Path(token_path).read_text, encoding="utf-8")
        ).strip()
    except FileNotFoundError:
        if token_path not in _missing_token_paths_warned:
            _missing_token_paths_warned.add(token_path)
            logger.warning(
                "Auth provider service-account token not found at %s; sending "
                "requests without %s (logged once per process)",
                token_path,
                SERVICE_ACCOUNT_TOKEN_HEADER,
            )
        return outbound_headers
    except (OSError, UnicodeError):
        # File errors can contain the mount path or token bytes; do not expose them.
        raise AuthenticationServiceUnavailableError(
            message="Unable to read auth provider service-account credentials"
        ) from None

    if token:
        # JWTs use base64url segments. Reject malformed bytes before an HTTP
        # library can echo an invalid header value in an exception.
        if re.fullmatch(r"[A-Za-z0-9._-]+", token) is None:
            raise AuthenticationServiceUnavailableError(
                message="Invalid auth provider service-account credentials"
            )
        outbound_headers[SERVICE_ACCOUNT_TOKEN_HEADER] = token
    return outbound_headers
