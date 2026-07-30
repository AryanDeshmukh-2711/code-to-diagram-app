from typing import Literal

from pydantic import BaseModel


class DependencyStatus(BaseModel):
    name: Literal["postgres", "redis", "plantuml"]
    ok: bool
    latency_ms: float
    error: str | None = None


class HealthReport(BaseModel):
    status: Literal["ok", "degraded"]
    dependencies: list[DependencyStatus]
