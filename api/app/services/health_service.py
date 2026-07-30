"""Dependency probes behind GET /health.

Each probe performs real I/O against its dependency. A health endpoint that
returns 200 without touching what it claims to be checking is worse than no
health endpoint at all, because it launders an outage into a green signal.
"""

import asyncio
import time
from collections.abc import Awaitable, Callable

import httpx
from sqlalchemy import text

from app.core.config import get_settings
from app.core.db import engine
from app.core.redis import redis_client
from app.schemas.health import DependencyStatus, HealthReport

_ERROR_MAX_CHARS = 200


async def _probe_postgres() -> None:
    async with engine.connect() as conn:
        await conn.execute(text("SELECT 1"))


async def _probe_redis() -> None:
    await redis_client.ping()


async def _probe_plantuml() -> None:
    # The server 302s from / to a rendered /uml/<encoded> page. Following the
    # redirect is the stronger check: a 200 there means it actually rendered a
    # diagram, not merely that the port is open.
    settings = get_settings()
    async with httpx.AsyncClient(
        timeout=settings.health_probe_timeout_seconds,
        follow_redirects=True,
    ) as client:
        response = await client.get(settings.plantuml_server_url)
        response.raise_for_status()


async def _run_probe(
    name: str,
    probe: Callable[[], Awaitable[None]],
) -> DependencyStatus:
    timeout = get_settings().health_probe_timeout_seconds
    started = time.perf_counter()
    try:
        async with asyncio.timeout(timeout):
            await probe()
    except Exception as exc:  # any failure, including timeout, is a failed dependency
        # Truncated and type-prefixed: connection errors can echo back a DSN,
        # and this response body is not authenticated.
        detail = f"{type(exc).__name__}: {exc}"[:_ERROR_MAX_CHARS]
        return DependencyStatus(
            name=name,
            ok=False,
            latency_ms=round((time.perf_counter() - started) * 1000, 2),
            error=detail,
        )
    return DependencyStatus(
        name=name,
        ok=True,
        latency_ms=round((time.perf_counter() - started) * 1000, 2),
    )


async def check_dependencies() -> HealthReport:
    """Probe postgres, redis and plantuml concurrently."""
    dependencies = await asyncio.gather(
        _run_probe("postgres", _probe_postgres),
        _run_probe("redis", _probe_redis),
        _run_probe("plantuml", _probe_plantuml),
    )

    status = "ok" if all(dep.ok for dep in dependencies) else "degraded"
    return HealthReport(status=status, dependencies=list(dependencies))
