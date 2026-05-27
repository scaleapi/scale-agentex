"""
SSRF guard for caller-supplied URLs that Agentex fetches/uploads to server-side.

Used by task retention endpoints that accept presigned URLs for export upload
and rehydrate download. A malicious or careless caller could otherwise point us
at internal services (databases, metadata IPs, private networks) — the guard
resolves the hostname and rejects any IP that's not publicly routable.
"""

import asyncio
import ipaddress
from urllib.parse import urlparse

from src.domain.exceptions import ClientError


async def validate_external_url(url: str) -> None:
    """
    Reject the URL if it would cause Agentex to issue a request to non-public
    infrastructure. Raises ClientError; returns None on success.

    Resolution happens here, but the subsequent request uses the hostname — DNS
    rebinding is possible (returning a public IP here and a private one at the
    actual request). The mitigation is acceptable for v1 because the realistic
    threat model is operator misconfiguration, not active attack from a
    privileged caller.
    """
    parsed = urlparse(url)

    if parsed.scheme != "https":
        raise ClientError(f"URL scheme must be 'https'; got '{parsed.scheme}'.")
    if not parsed.hostname:
        raise ClientError("URL must include a hostname.")

    loop = asyncio.get_event_loop()
    try:
        infos = await loop.getaddrinfo(parsed.hostname, parsed.port or 443)
    except OSError as e:
        raise ClientError(f"Could not resolve hostname '{parsed.hostname}': {e}") from e

    for info in infos:
        addr_str = info[4][0]
        addr = ipaddress.ip_address(addr_str)
        if (
            addr.is_private
            or addr.is_loopback
            or addr.is_link_local
            or addr.is_reserved
            or addr.is_multicast
            or addr.is_unspecified
        ):
            raise ClientError(
                f"URL '{url}' resolves to a non-public address ({addr}); "
                f"refusing to issue a server-side request."
            )
