"""The LLM Gateway.

One interface — ``complete(task_name, input, schema)`` — returning a validated
object or raising. Callers never see a provider, a model name, a prompt, or a
raw string that might be JSON.

The contract, precisely:

* **Validated or nothing.** The caller's Pydantic model is the judge. A
  half-parsed dict is never returned.
* **One corrective retry, then stop.** The retry names the failing field and
  echoes the rejected output, because "that was wrong, try again" gives the
  model nothing to correct against. After the second failure it raises — a
  loop that keeps paying for generations until something parses is how a
  runaway bill happens.
* **Every attempt accounted for**, failures included, before the error
  propagates (NFR-M3).
* **Caller supplies data, never instructions.** Prompts come from task config.
"""

import logging
import re
from collections.abc import Mapping
from time import perf_counter
from typing import TypeVar

from pydantic import BaseModel, ValidationError

from llm.config import TASKS, TaskConfig
from llm.errors import ProviderError, SchemaValidationFailed, UnknownTaskError
from llm.pricing import estimate_cost_usd
from llm.prompting import build_correction, build_system_prompt, build_user_message
from llm.providers.base import Provider, ProviderRequest
from llm.schema import to_response_schema
from llm.telemetry import CallRecord, CallSink, LoggingSink

logger = logging.getLogger(__name__)

T = TypeVar("T", bound=BaseModel)

MAX_ATTEMPTS = 2
"""One generation, one corrective retry. Not configurable on purpose: an
unbounded retry budget on a paid or slow backend is a footgun, and the
corrective retry either works or the input needs a human."""

_FENCED = re.compile(r"```(?:json)?\s*(.*?)```", re.DOTALL)


class LLMGateway:
    def __init__(
        self,
        providers: Mapping[str, Provider],
        tasks: Mapping[str, TaskConfig] | None = None,
        sink: CallSink | None = None,
    ) -> None:
        self._providers = dict(providers)
        self._tasks = dict(tasks) if tasks is not None else dict(TASKS)
        self._sink = sink or LoggingSink()

    async def complete(
        self,
        task_name: str,
        input: str,
        schema: type[T],
        *,
        user_id: str | None = None,
    ) -> T:
        """Run ``task_name`` over ``input`` and return a validated ``schema``."""
        task = self._task(task_name)
        provider = self._provider(task)

        system = build_system_prompt(task)
        json_schema = to_response_schema(schema)

        correction: str | None = None
        last_output = ""
        last_detail = ""

        for attempt in range(1, MAX_ATTEMPTS + 1):
            request = ProviderRequest(
                model=task.model,
                system=system,
                user=build_user_message(input, correction),
                json_schema=json_schema,
                max_tokens=task.max_tokens,
                temperature=task.temperature,
                timeout_seconds=task.timeout_seconds,
            )

            started = perf_counter()
            try:
                response = await provider.generate(request)
            except Exception as exc:
                self._record(task_name, task, attempt, "provider_error", 0, 0, started, user_id)
                if isinstance(exc, ProviderError):
                    raise
                raise ProviderError(
                    f"provider {task.provider!r} failed on task {task_name!r}: "
                    f"{type(exc).__name__}: {exc}"
                ) from exc

            try:
                validated = schema.model_validate_json(_extract_json(response.text))
            except (ValidationError, ValueError) as exc:
                self._record(
                    task_name,
                    task,
                    attempt,
                    "schema_invalid",
                    response.input_tokens,
                    response.output_tokens,
                    started,
                    user_id,
                )
                last_output = response.text
                last_detail = _format_validation_error(exc)
                correction = build_correction(last_output, last_detail)
                logger.warning(
                    "task %s attempt %d produced output failing schema validation: %s",
                    task_name,
                    attempt,
                    last_detail,
                )
                continue

            self._record(
                task_name,
                task,
                attempt,
                "ok",
                response.input_tokens,
                response.output_tokens,
                started,
                user_id,
            )
            return validated

        raise SchemaValidationFailed(task_name, last_output, last_detail)

    # -- internals ---------------------------------------------------------

    def _task(self, name: str) -> TaskConfig:
        try:
            return self._tasks[name]
        except KeyError:
            raise UnknownTaskError(name, list(self._tasks)) from None

    def _provider(self, task: TaskConfig) -> Provider:
        try:
            return self._providers[task.provider]
        except KeyError:
            raise ProviderError(
                f"no provider registered under {task.provider!r}; "
                f"registered: {', '.join(sorted(self._providers)) or 'none'}"
            ) from None

    def _record(
        self,
        task_name: str,
        task: TaskConfig,
        attempt: int,
        outcome: str,
        input_tokens: int,
        output_tokens: int,
        started: float,
        user_id: str | None,
    ) -> None:
        self._sink.record(
            CallRecord(
                task=task_name,
                provider=task.provider,
                model=task.model,
                attempt=attempt,
                outcome=outcome,  # type: ignore[arg-type]
                input_tokens=input_tokens,
                output_tokens=output_tokens,
                latency_ms=(perf_counter() - started) * 1000,
                cost_usd=estimate_cost_usd(task.model, input_tokens, output_tokens),
                user_id=user_id,
            )
        )


def _extract_json(text: str) -> str:
    """Pull the JSON object out of a response.

    Constrained decoding usually makes this a no-op, but small local models
    still wrap output in ``` fences or a sentence of preamble often enough that
    failing the whole run over it would waste a generation for nothing.
    """
    candidate = text.strip()

    fenced = _FENCED.search(candidate)
    if fenced:
        candidate = fenced.group(1).strip()

    start = candidate.find("{")
    end = candidate.rfind("}")
    if start != -1 and end > start:
        return candidate[start : end + 1]
    return candidate


def _format_validation_error(exc: Exception) -> str:
    if isinstance(exc, ValidationError):
        return "\n".join(
            f"- {'.'.join(str(part) for part in error['loc']) or '<root>'}: {error['msg']}"
            for error in exc.errors()
        )
    return f"- response was not valid JSON: {exc}"


def build_default_gateway(sink: CallSink | None = None) -> LLMGateway:
    """A gateway wired from the environment.

    Both adapters are registered, so switching backend is an LLM_PROVIDER
    change with no code edit anywhere (NFR-M1).
    """
    import os

    from llm.providers.ollama import DEFAULT_BASE_URL, OllamaProvider
    from llm.providers.openai_compatible import OpenAICompatibleProvider

    providers: dict[str, Provider] = {
        "ollama": OllamaProvider(base_url=os.getenv("LLM_BASE_URL", DEFAULT_BASE_URL)),
    }

    openai_base_url = os.getenv("LLM_OPENAI_BASE_URL")
    if openai_base_url:
        providers["openai_compatible"] = OpenAICompatibleProvider(
            base_url=openai_base_url,
            api_key=os.getenv("LLM_API_KEY") or None,
        )

    return LLMGateway(providers=providers, sink=sink)
