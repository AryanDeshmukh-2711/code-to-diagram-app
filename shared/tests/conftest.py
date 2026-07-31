import copy
import os
from typing import Any

import pytest
from sqlalchemy import text
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

from cpm.fixtures import library_management_system_payload
from store.models import Base
from store.session import database_url


@pytest.fixture
def payload() -> dict[str, Any]:
    """A deep copy of the Library Management System fixture.

    Deep-copied so a test can mutate it into an invalid state without leaking
    that mutation into the next test.
    """
    return copy.deepcopy(library_management_system_payload())


@pytest.fixture
def db_schema(request) -> str:
    """One schema per test module, so two db-backed files cannot collide."""
    return f"t_{request.module.__name__.rsplit('.', 1)[-1]}"


@pytest.fixture
async def session_factory(db_schema):
    """A throwaway schema on the real database, dropped afterwards.

    Real Postgres on purpose: the guarantees these tests exist for — the
    uq_run_artefact upsert, ON CONFLICT semantics — live in the database, so a
    fake session factory would only prove that a mock behaves like a mock.
    A private schema keeps development data out of reach and sidesteps the FR-7
    immutability rules on cpm_versions, which would otherwise block cleanup.
    """
    url = os.getenv("TEST_DATABASE_URL", database_url())
    engine = create_async_engine(url)
    try:
        async with engine.begin() as connection:
            await connection.execute(text(f"DROP SCHEMA IF EXISTS {db_schema} CASCADE"))
            await connection.execute(text(f"CREATE SCHEMA {db_schema}"))
    except Exception as exc:  # pragma: no cover - environment, not logic
        await engine.dispose()
        pytest.skip(f"no Postgres at {url}: {type(exc).__name__}: {exc}")

    scoped = engine.execution_options(schema_translate_map={None: db_schema})
    async with scoped.begin() as connection:
        await connection.run_sync(Base.metadata.create_all)

    yield async_sessionmaker(scoped, expire_on_commit=False)

    async with engine.begin() as connection:
        await connection.execute(text(f"DROP SCHEMA IF EXISTS {db_schema} CASCADE"))
    await engine.dispose()
