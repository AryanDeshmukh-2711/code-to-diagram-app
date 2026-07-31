"""Sessions, in exchange for a key.

Deliberately small. There is no password, no reset flow and no email: an
account is issued a high-entropy API key once and trades it for a short-lived
signed session. That proves who is calling, which is all the rest of the system
needs, and it adds no surface that has to be got right about storing or
recovering human-chosen secrets.
"""

import uuid

from fastapi import APIRouter, HTTPException, status
from pydantic import BaseModel
from store.models import AccountRow
from store.session import SessionFactory

from app.core.identity import SESSION_TTL_SECONDS, issue_session, new_api_key, verify_api_key

router = APIRouter(prefix="/auth", tags=["auth"])


class RegisterIn(BaseModel):
    email: str | None = None
    tier: str = "free"


class RegisterOut(BaseModel):
    accountId: str
    apiKey: str
    note: str = "Store this key now. It is not recoverable and will not be shown again."


class TokenIn(BaseModel):
    accountId: str
    apiKey: str


class TokenOut(BaseModel):
    token: str
    expiresInSeconds: int


@router.post("/register", response_model=RegisterOut, status_code=status.HTTP_201_CREATED)
async def register(body: RegisterIn) -> RegisterOut:
    """Create an account and issue its one key."""
    key, key_hash, salt = new_api_key()
    account_id = f"acct_{uuid.uuid4().hex[:20]}"

    async with SessionFactory() as session:
        session.add(
            AccountRow(
                id=account_id,
                email=body.email,
                tier=body.tier,
                api_key_hash=key_hash,
                api_key_salt=salt,
            )
        )
        await session.commit()

    return RegisterOut(accountId=account_id, apiKey=key)


@router.post("/token", response_model=TokenOut)
async def token(body: TokenIn) -> TokenOut:
    """Trade the key for a session.

    One message for both an unknown account and a wrong key: telling them apart
    would confirm which account ids exist.
    """
    async with SessionFactory() as session:
        account = await session.get(AccountRow, body.accountId)

    if account is None or not verify_api_key(
        body.apiKey, account.api_key_hash, account.api_key_salt
    ):
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, detail="unknown account or incorrect key")

    return TokenOut(token=issue_session(account.id), expiresInSeconds=SESSION_TTL_SECONDS)
