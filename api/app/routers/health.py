from fastapi import APIRouter, Response, status

from app.schemas.health import HealthReport
from app.services.health_service import check_dependencies

router = APIRouter(tags=["health"])


@router.get("/health", response_model=HealthReport)
async def health(response: Response) -> HealthReport:
    """Readiness: reports postgres, redis and plantuml. 503 if any is down."""
    report = await check_dependencies()
    if report.status != "ok":
        response.status_code = status.HTTP_503_SERVICE_UNAVAILABLE
    return report


@router.get("/health/live")
async def live() -> dict[str, str]:
    """Liveness: the process is up. Used by the container healthcheck.

    Deliberately does not touch dependencies — otherwise a PlantUML outage
    would make Docker restart a perfectly healthy API container.
    """
    return {"status": "ok"}
