"""Smoke tests for the scaffold.

Liveness is asserted directly. Readiness is asserted with the dependency
probes patched, so `make test` does not require a running stack — but note
the probes themselves are never stubbed in a way that would let a real
outage pass silently at runtime.
"""

import httpx
import pytest

from app.main import app
from app.schemas.health import DependencyStatus, HealthReport


@pytest.fixture
async def client() -> httpx.AsyncClient:
    transport = httpx.ASGITransport(app=app)
    async with httpx.AsyncClient(transport=transport, base_url="http://test") as ac:
        yield ac


async def test_liveness_does_not_touch_dependencies(client: httpx.AsyncClient) -> None:
    response = await client.get("/health/live")
    assert response.status_code == 200
    assert response.json() == {"status": "ok"}


async def test_health_reports_all_three_dependencies(
    client: httpx.AsyncClient,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    async def fake_check() -> HealthReport:
        return HealthReport(
            status="ok",
            dependencies=[
                DependencyStatus(name="postgres", ok=True, latency_ms=1.0),
                DependencyStatus(name="redis", ok=True, latency_ms=1.0),
                DependencyStatus(name="plantuml", ok=True, latency_ms=1.0),
            ],
        )

    monkeypatch.setattr("app.routers.health.check_dependencies", fake_check)

    response = await client.get("/health")

    assert response.status_code == 200
    names = {dep["name"] for dep in response.json()["dependencies"]}
    assert names == {"postgres", "redis", "plantuml"}


async def test_health_returns_503_when_a_dependency_is_down(
    client: httpx.AsyncClient,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    async def fake_check() -> HealthReport:
        return HealthReport(
            status="degraded",
            dependencies=[
                DependencyStatus(name="postgres", ok=True, latency_ms=1.0),
                DependencyStatus(name="redis", ok=True, latency_ms=1.0),
                DependencyStatus(
                    name="plantuml", ok=False, latency_ms=3000.0, error="ConnectError: refused"
                ),
            ],
        )

    monkeypatch.setattr("app.routers.health.check_dependencies", fake_check)

    response = await client.get("/health")

    assert response.status_code == 503
    assert response.json()["status"] == "degraded"
