"""LLM Gateway — the only module permitted to know a model name.

Constraint C-2. Callers depend on `LLMGateway.complete(task, input, schema)`
and nothing else; which backend serves it, which model, and what the prompt
looks like are all internal.

`shared/tests/test_no_hardcoded_models.py` enforces this by scanning the whole
repository for model identifiers and provider SDK imports outside this package.
"""

from llm.config import TASKS, TaskConfig, get_task
from llm.errors import (
    LLMError,
    ProviderError,
    SchemaValidationFailed,
    UnknownTaskError,
)
from llm.gateway import LLMGateway, build_default_gateway
from llm.pricing import estimate_cost_usd
from llm.telemetry import CallRecord, CallSink, LoggingSink, RecordingSink

__all__ = [
    "TASKS",
    "CallRecord",
    "CallSink",
    "LLMError",
    "LLMGateway",
    "LoggingSink",
    "ProviderError",
    "RecordingSink",
    "SchemaValidationFailed",
    "TaskConfig",
    "UnknownTaskError",
    "build_default_gateway",
    "estimate_cost_usd",
    "get_task",
]
