import logging
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.core.config import get_settings
from app.core.db import engine
from app.core.redis import redis_client
from app.routers import chat, exports, extraction, health, projects, review, runs


@asynccontextmanager
async def lifespan(app: FastAPI) -> AsyncIterator[None]:
    yield
    await redis_client.aclose()
    await engine.dispose()


def create_app() -> FastAPI:
    settings = get_settings()
    logging.basicConfig(level=settings.log_level)

    app = FastAPI(
        title="AI Software Architect API",
        version="0.1.0",
        lifespan=lifespan,
    )

    app.add_middleware(
        CORSMiddleware,
        allow_origins=["http://localhost:3000"],
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
    )

    app.include_router(health.router)
    app.include_router(projects.router)
    app.include_router(extraction.router)
    app.include_router(review.router)
    app.include_router(chat.router)
    app.include_router(runs.router)
    app.include_router(exports.router)
    app.include_router(exports.templates_router)
    app.include_router(exports.artefact_router)
    app.include_router(exports.metrics_router)
    return app


app = create_app()
