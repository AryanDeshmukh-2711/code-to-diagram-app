"""Failure modes of the LLM Gateway.

Distinct types because callers respond differently: a provider being down is
retryable infrastructure, a schema violation after the corrective retry is a
failed generation run, and an unknown task is a programming error.
"""


class LLMError(Exception):
    """Base class for every gateway failure."""


class UnknownTaskError(LLMError):
    """A task name that is not in the registry — a typo or a missing config entry."""

    def __init__(self, name: str, known: list[str]) -> None:
        super().__init__(f"unknown LLM task {name!r}; known tasks: {', '.join(sorted(known))}")
        self.name = name


class ProviderError(LLMError):
    """The provider could not be reached, or answered with an error.

    Never carries credentials: the message is assembled from status and
    provider-supplied text only, because it is logged and can surface in a
    failed run's diagnostics.
    """


class SchemaValidationFailed(LLMError):
    """The model produced output that does not satisfy the caller's schema.

    Raised only after the corrective retry has also failed — the gateway fails
    loudly rather than handing back a half-parsed object.
    """

    def __init__(self, task_name: str, raw_output: str, detail: str) -> None:
        super().__init__(
            f"task {task_name!r} returned output that failed schema validation twice: "
            f"{detail}\nlast raw output: {raw_output[:500]!r}"
        )
        self.task_name = task_name
        self.raw_output = raw_output
