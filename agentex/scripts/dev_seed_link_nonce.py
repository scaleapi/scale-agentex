#!/usr/bin/env python3
"""DEV ONLY: seed a link nonce and print the URL to click.

Exists because three steps of the identity-link flow can only be exercised by a real
browser, and no script can stand in for them:

  1. Does the SGP session cookie actually reach agentex? The cookie is scoped to a
     parent domain, so it only travels if the agentex host is a sibling subdomain of
     the SGP host — worth confirming rather than assuming.
  2. Does agentex's auth middleware turn that cookie into a principal?
  3. Will identity-service mint a key for it? ``POST /api-keys`` is guarded by
     ``CustomerIdentityJwtGuard``, which reads ``_identityJwt`` / ``_jwt`` **cookies**
     and rejects ``x-api-key`` outright — so an API key cannot substitute.

This writes a nonce exactly as the Slack leg would (same service, same payload
shape), then prints the link. Clicking it runs the genuine callback: confirmation
page, mint, encrypt, store.

    # against a locally running API
    ./scripts/dev_seed_link_nonce.py --slack-user U01ABCDEF --team T01EXAMPLE

    # against a deployed API (your browser's session cookie must cover that host)
    ./scripts/dev_seed_link_nonce.py --slack-user U01ABCDEF --team T01EXAMPLE \
        --base-url https://<agentex-host>

Requires REDIS_URL (the nonce store the callback will read from). Seeds nothing
sensitive: a nonce holds provider ids and the pending message, never a credential.
"""

from __future__ import annotations

import argparse
import asyncio
import os
import sys
from pathlib import Path
from urllib.parse import urlencode

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from src.domain.services.link_nonce_service import (  # noqa: E402
    LinkNonceService,
    LinkRequest,
)


async def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    parser.add_argument("--slack-user", required=True, help="Slack member ID (U…)")
    parser.add_argument("--team", required=True, help="Slack team ID (T…)")
    parser.add_argument(
        "--display-name",
        default="",
        help="Shown on the confirmation screen; defaults to the Slack user id",
    )
    parser.add_argument(
        "--message",
        default="what's in my notion?",
        help="Pending turn stashed on the nonce (replayed after linking)",
    )
    parser.add_argument(
        "--base-url",
        default=os.getenv("AGENTEX_BASE_URL", "http://localhost:5003"),
        help="Where the agentex API is reachable from your browser",
    )
    parser.add_argument(
        "--redis-url",
        default=os.getenv("REDIS_URL", "redis://localhost:6379"),
        help="Nonce store the callback will read (must match the API's REDIS_URL)",
    )
    args = parser.parse_args()

    try:
        import redis.asyncio as redis
    except ImportError:
        print("redis package not available", file=sys.stderr)
        return 1

    client = redis.Redis.from_url(args.redis_url)
    try:
        await client.ping()
    except Exception as exc:  # noqa: BLE001
        print(f"cannot reach Redis at {args.redis_url}: {exc}", file=sys.stderr)
        print(
            "start the dev stack first (./dev.sh), or pass --redis-url", file=sys.stderr
        )
        return 1

    token = await LinkNonceService(redis_client=client).create(
        LinkRequest(
            provider="slack",
            external_team_id=args.team,
            external_user_id=args.slack_user,
            display_name=args.display_name or args.slack_user,
            pending_turn={
                "team_id": args.team,
                "channel": "C_DEV",
                "user": args.slack_user,
                "text": args.message,
                "thread_ts": "1700000000.000100",
                "selector": None,
            },
        )
    )
    await client.aclose()

    url = f"{args.base_url.rstrip('/')}/integrations/slack/link?{urlencode({'nonce': token})}"
    print()
    print("Open this in a browser that is SIGNED IN to SGP:")
    print()
    print(f"  {url}")
    print()
    print("What to look for:")
    print("  * the confirmation page naming BOTH identities  -> cookie reached agentex")
    print("    and the middleware resolved a principal")
    print(
        "  * after Connect: 'You're connected'             -> identity-service minted"
    )
    print("    an ssk_ key and it is stored encrypted")
    print("  * 'Please sign in to SGP' (401)                 -> the cookie did NOT")
    print("    arrive; check the cookie domain against this base-url's host")
    print()
    print("Then verify what landed:")
    print(
        '  psql "$DATABASE_URL" -c "SELECT external_user_id, sgp_user_id, linked_via, '
        "credential_expires_at, (credential_ciphertext IS NOT NULL) AS has_key "
        'FROM identity_links WHERE revoked_at IS NULL;"'
    )
    print()
    return 0


if __name__ == "__main__":
    raise SystemExit(asyncio.run(main()))
