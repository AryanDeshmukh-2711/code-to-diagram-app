"""arq worker entrypoint.

Run with: arq worker.main.WorkerSettings

Every long-running generation stage executes here, never in the HTTP request
cycle (constraint C-4).
"""

import logging
import os
from typing import Any

from worker.handlers.assemble import assemble_document
from worker.handlers.extract import extract_cpm
from worker.handlers.render import regenerate_diagram, render_run
from worker.settings import redis_settings as get_redis_settings

logging.basicConfig(level=os.getenv("LOG_LEVEL", "INFO"))
logger = logging.getLogger(__name__)


async def startup(ctx: dict[str, Any]) -> None:
    logger.info("worker started")


async def shutdown(ctx: dict[str, Any]) -> None:
    logger.info("worker stopped")


class WorkerSettings:
    functions = [extract_cpm, render_run, regenerate_diagram, assemble_document]
    redis_settings = get_redis_settings()
    on_startup = startup
    on_shutdown = shutdown
    max_jobs = 10
    job_timeout = 300
