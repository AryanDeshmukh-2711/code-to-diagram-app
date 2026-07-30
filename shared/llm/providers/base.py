"""The provider contract.

Everything the gateway needs from a backend, and nothing about who that backend
is. Swapping providers is a registry entry, so NFR-M1 holds: no calling code
changes.

Adapters return text plus token counts. Parsing and validation stay in the
gateway, so every provider is held to the same guarantee rather than each one
reimplementing it slightly differently.
"""

from dataclasses import dataclass
from typing import Any, Protocol


@dataclass(frozen=True)
class ProviderRequest:
    model: str
    system: str
    user: str
    json_schema: dict[str, Any] | None
    max_tokens: int
    temperature: float | None
    timeout_seconds: float


@dataclass(frozen=True)
class ProviderResponse:
    text: str
    input_tokens: int
    output_tokens: int
    model: str


class Provider(Protocol):
    """One backend. Implementations must not raise anything but ProviderError."""

    name: str

    async def generate(self, request: ProviderRequest) -> ProviderResponse: ...
