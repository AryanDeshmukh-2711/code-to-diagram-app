"""Signed, expiring links to a diagram or a finished export (NFR-S4).

The signature covers the artefact id and the deadline, so a link cannot be
edited into a link for somebody else's diagram, and a link that leaks in a
shared screenshot stops working.

This app is a single-user, local-first tool — there is no account system and
nothing to authenticate a caller against. `sign`/`verify` are the one thing
here that still needs a secret: an artefact id alone would let anyone who can
guess or enumerate one fetch it, and a link is meant to work when pasted
somewhere else (embedded, opened in a new tab), so it carries its own proof
rather than relying on a session.
"""

import hashlib
import hmac
import os
import time
from base64 import urlsafe_b64decode, urlsafe_b64encode

from fastapi import HTTPException, status

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


def _not_found(kind: str, identifier: str) -> HTTPException:
    return HTTPException(status.HTTP_404_NOT_FOUND, detail=f"no {kind} {identifier!r}")


async def get_or_404(session, model, id_: str, kind: str):
    """The row, or a 404 named after what was being looked for.

    Every route used to look a row up and then check it belonged to the
    caller; with one implicit local user there is nothing left to check
    belonging against, so this is just the lookup half of that, kept as one
    helper so a route body still reads the same way it always did.
    """
    row = await session.get(model, id_)
    if row is None:
        raise _not_found(kind, id_)
    return row
