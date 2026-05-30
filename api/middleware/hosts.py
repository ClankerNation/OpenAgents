"""Trusted-host validation middleware for the OpenAgents API.

Inspects the ``Host`` header on every inbound request and rejects it
with a 400 if the value does not match the approved host registry.
Supports exact literal matches and structured subdomain wildcards
(e.g. ``*.openagents.ai``).  Port suffixes are stripped automatically
so ``localhost:8000`` matches an ``localhost`` entry.
"""

import logging
import os
from typing import List

from starlette.middleware.base import BaseHTTPMiddleware
from starlette.requests import Request
from starlette.responses import PlainTextResponse, Response

logger = logging.getLogger("openagents.hosts")


# ---------------------------------------------------------------------------
# Host-matching helpers
# ---------------------------------------------------------------------------

def _parse_allowed_hosts(raw: str) -> List[str]:
    """Split, strip, lowercase, and remove empty entries."""
    return [
        h.strip().lower()
        for h in raw.split(",")
        if h.strip()
    ]


def _strip_port(host: str) -> str:
    """Remove an optional ``:port`` suffix from a host value.

    Handles IPv6 bracket notation (``[::1]:8000``) by only stripping
    a port that appears *after* the closing bracket.
    """
    if host.startswith("["):
        # IPv6 literal — port follows the closing bracket
        bracket_end = host.find("]")
        if bracket_end != -1:
            after = host[bracket_end + 1:]
            if after.startswith(":"):
                return host[: bracket_end + 1]
        return host

    # IPv4 / hostname — last colon is the port separator
    colon = host.rfind(":")
    if colon != -1:
        return host[:colon]
    return host


def host_matches(host_header: str, allowed_hosts: List[str]) -> bool:
    """Return ``True`` if *host_header* passes the allow-list.

    Matching rules:
    * ``"*"`` in the allow-list permits any host.
    * An exact case-insensitive match passes.
    * A wildcard entry like ``*.example.com`` matches any subdomain of
      ``example.com`` (but **not** ``example.com`` itself).
    """
    hostname = _strip_port(host_header).lower()

    for pattern in allowed_hosts:
        if pattern == "*":
            return True
        if pattern == hostname:
            return True
        if pattern.startswith("*."):
            # ``*.example.com`` → the suffix that must follow a subdomain
            suffix = pattern[1:]  # ".example.com"
            if hostname.endswith(suffix) and hostname != suffix.lstrip("."):
                return True

    return False


# ---------------------------------------------------------------------------
# Middleware
# ---------------------------------------------------------------------------

class TrustedHostMiddleware(BaseHTTPMiddleware):
    """Rejects requests whose ``Host`` header is not in the approved list.

    Parameters
    ----------
    app:
        The ASGI application to wrap.
    allowed_hosts:
        Pre-parsed list of allowed host patterns.  If ``None``, the list
        is read from the ``ALLOWED_HOSTS`` environment variable at
        construction time.
    """

    def __init__(self, app, allowed_hosts: List[str] = None):
        super().__init__(app)
        if allowed_hosts is not None:
            self.allowed_hosts = [h.lower() for h in allowed_hosts]
        else:
            raw = os.environ.get("ALLOWED_HOSTS", "")
            self.allowed_hosts = _parse_allowed_hosts(raw)

    async def dispatch(self, request: Request, call_next) -> Response:
        host_header = request.headers.get("host", "")

        if not host_header or not host_matches(host_header, self.allowed_hosts):
            logger.warning(
                "Rejected request with untrusted Host header: %r",
                host_header,
            )
            return PlainTextResponse("Invalid Host Header", status_code=400)

        return await call_next(request)
