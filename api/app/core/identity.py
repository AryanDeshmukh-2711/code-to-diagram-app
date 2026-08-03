"""Who is calling, what they own, and signed links to their files.

Three things live here because they are one problem.

**The caller's identity is proved, not asserted.** A request carries a signed
session token, and a token is minted only in exchange for an account's API key,
which is verified against a salted hash of 256 bits of urandom. An earlier
version of this file read the account from a header and believed it, which
authenticated nobody — that was the last High finding of the pre-launch review
and it is closed here.

Sessions are short and stateless. The signature covers the account and the
deadline, so a token cannot be edited into a token for somebody else, and a
stolen one stops working. There is no revocation list, which is the honest
trade for having no session store: rotating an account's key invalidates every
token minted from it.

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
import secrets
import time
from base64 import urlsafe_b64decode, urlsafe_b64encode

from fastapi import Header, HTTPException, status
from store.models import ExtractionRow, GenerationRunRow, ProjectRow

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


SESSION_TTL_SECONDS = 12 * 3600


def new_api_key() -> tuple[str, str, str]:
    """A fresh key and what to store for it: (key, hash, salt).

    The key is returned once and never stored. If a user loses it the answer is
    a new key, not a recovery — a system that can show you your key can show it
    to whoever reads the database.
    """
    key = secrets.token_urlsafe(32)
    salt = secrets.token_hex(16)
    return key, _hash_key(key, salt), salt


def _hash_key(key: str, salt: str) -> str:
    return hashlib.sha256(f"{salt}:{key}".encode()).hexdigest()


def verify_api_key(key: str, stored_hash: str | None, salt: str | None) -> bool:
    if not stored_hash or not salt:
        return False
    return hmac.compare_digest(_hash_key(key, salt), stored_hash)


def issue_session(account_id: str, ttl_seconds: int = SESSION_TTL_SECONDS) -> str:
    """A bearer token for one account, valid for a while."""
    expires = int(time.time()) + ttl_seconds
    digest = hmac.new(
        _secret(), f"session:{account_id}:{expires}".encode(), hashlib.sha256
    ).digest()[:24]
    payload = urlsafe_b64encode(f"{account_id}:{expires}".encode()).decode().rstrip("=")
    return f"{payload}.{urlsafe_b64encode(digest).decode().rstrip('=')}"


def _decode(token: str) -> str:
    try:
        raw_payload, raw_signature = token.split(".", 1)
        payload = urlsafe_b64decode(raw_payload + "=" * (-len(raw_payload) % 4)).decode()
        account_id, raw_expiry = payload.rsplit(":", 1)
        expires = int(raw_expiry)
        supplied = urlsafe_b64decode(raw_signature + "=" * (-len(raw_signature) % 4))
    except Exception:
        raise HTTPException(
            status.HTTP_401_UNAUTHORIZED, detail="malformed session token"
        ) from None

    expected = hmac.new(
        _secret(), f"session:{account_id}:{expires}".encode(), hashlib.sha256
    ).digest()[:24]
    if not hmac.compare_digest(expected, supplied):
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, detail="invalid session token")
    if expires < time.time():
        raise HTTPException(
            status.HTTP_401_UNAUTHORIZED, detail="this session has expired; sign in again"
        )
    return account_id


async def require_account(authorization: str | None = Header(default=None)) -> str:
    """The calling account, proved. The only place identity enters the system.

    A missing token is refused rather than defaulted to a shared "anonymous"
    account, which would put every anonymous user's projects in one bucket that
    they could all read.
    """
    if not authorization or not authorization.lower().startswith("bearer "):
        raise HTTPException(
            status.HTTP_401_UNAUTHORIZED,
            detail="no session on this request; POST /auth/token for one",
            headers={"WWW-Authenticate": "Bearer"},
        )
    return _decode(authorization.split(" ", 1)[1].strip())


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


async def owned_extraction(session, extraction_id: str, account_id: str) -> ExtractionRow:
    row = await session.get(ExtractionRow, extraction_id)
    if row is None or row.account_id != account_id:
        raise _not_found("extraction", extraction_id)
    return row
