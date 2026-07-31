"""Who is calling, what they own, and signed links to their files.

Three things live here because they are one problem.

**The caller's identity has exactly one source.** It is read from a header, in
this module, and nowhere else. Before this, every endpoint took `accountId`
out of the request body — which meant a caller could name any account they
liked and the server believed them. Bodies are data; identity is not.

This is the seam where a real authentication provider plugs in. Today it reads
a header, which authenticates nobody: it stops accidental cross-account access
and makes ownership checkable, and it does not stop a determined attacker.
That gap is a launch blocker, recorded as such, and it is one function deep.

**Ownership is checked, and a miss looks like a miss.** Asking for someone
else's run returns 404, not 403: a 403 confirms the id exists, which is a
membership oracle over every project on the platform.

**Artefact links are signed and expire (NFR-S4).** The signature covers the
artefact id and the deadline, so a link cannot be edited into a link for
somebody else's diagram, and a link that leaks in a shared screenshot stops
working.
"""

import hashlib
import hmac
import os
import time
from base64 import urlsafe_b64decode, urlsafe_b64encode

from fastapi import Header, HTTPException, status
from store.models import GenerationRunRow, ProjectRow

SECRET = os.getenv("ASA_SIGNING_SECRET", "").encode() or None
DEFAULT_TTL_SECONDS = 900


class SigningNotConfigured(RuntimeError):
    """No secret. Refused rather than defaulted.

    A development default would be committed, deployed, and then every signed
    URL on the platform would be forgeable by anyone who had read the source.
    """


def _secret() -> bytes:
    if SECRET is None:
        raise SigningNotConfigured(
            "ASA_SIGNING_SECRET is not set; artefact links cannot be signed. "
            "Set it to a random 32-byte value."
        )
    return SECRET


def sign(artefact_id: str, ttl_seconds: int = DEFAULT_TTL_SECONDS) -> str:
    """A token for one artefact, valid for a while."""
    expires = int(time.time()) + ttl_seconds
    message = f"{artefact_id}:{expires}".encode()
    digest = hmac.new(_secret(), message, hashlib.sha256).digest()[:20]
    return f"{expires}.{urlsafe_b64encode(digest).decode().rstrip('=')}"


def verify(artefact_id: str, token: str) -> None:
    """Raise unless this token was minted for this artefact and still valid."""
    try:
        raw_expiry, signature = token.split(".", 1)
        expires = int(raw_expiry)
    except (ValueError, AttributeError):
        raise HTTPException(status.HTTP_403_FORBIDDEN, detail="malformed link") from None

    message = f"{artefact_id}:{expires}".encode()
    expected = hmac.new(_secret(), message, hashlib.sha256).digest()[:20]
    padded = signature + "=" * (-len(signature) % 4)
    try:
        supplied = urlsafe_b64decode(padded.encode())
    except Exception:
        raise HTTPException(status.HTTP_403_FORBIDDEN, detail="malformed link") from None

    # Constant time: a comparison that returns early leaks the signature one
    # byte at a time to anyone willing to measure.
    if not hmac.compare_digest(expected, supplied):
        raise HTTPException(status.HTTP_403_FORBIDDEN, detail="invalid link")
    if expires < time.time():
        raise HTTPException(status.HTTP_403_FORBIDDEN, detail="this link has expired")


async def require_account(x_account_id: str | None = Header(default=None)) -> str:
    """The calling account. The only place identity enters the system.

    A missing header is refused rather than defaulted to a shared "anonymous"
    account — which would put every anonymous user's projects in one bucket
    that they could all read.
    """
    if not x_account_id or not x_account_id.strip():
        raise HTTPException(
            status.HTTP_401_UNAUTHORIZED,
            detail="no account on this request; send X-Account-Id",
        )
    return x_account_id.strip()


def _not_found(kind: str, identifier: str) -> HTTPException:
    return HTTPException(status.HTTP_404_NOT_FOUND, detail=f"no {kind} {identifier!r}")


async def owned_project(session, project_id: str, account_id: str) -> ProjectRow | None:
    """The project, if this account owns it. 404 otherwise, never 403."""
    project = await session.get(ProjectRow, project_id)
    if project is None:
        # Not yet created: the caller may be about to create it.
        return None
    if project.account_id != account_id:
        raise _not_found("project", project_id)
    return project


async def owned_run(session, run_id: str, account_id: str) -> GenerationRunRow:
    run = await session.get(GenerationRunRow, run_id)
    if run is None or (run.account_id is not None and run.account_id != account_id):
        raise _not_found("run", run_id)
    return run
