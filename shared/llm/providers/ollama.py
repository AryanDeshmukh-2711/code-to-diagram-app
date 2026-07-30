"""Ollama — local inference.

Free, no API key, no quota, and nothing leaves the machine, which is what makes
the no-training-on-user-content requirement (SRS §6.3, §9.2) structurally true
rather than contractually promised.

Ollama constrains decoding to the supplied JSON schema via its `format` field,
so structured output is enforced during generation rather than hoped for and
checked afterwards.
"""

import logging
from typing import Any

import httpx

from llm.errors import ProviderError
from llm.providers.base import ProviderRequest, ProviderResponse

logger = logging.getLogger(__name__)

DEFAULT_BASE_URL = "http://host.docker.internal:11434"
"""Ollama runs on the host, not in a container, so it can reach the GPU.
`host.docker.internal` is how the api and worker containers find it."""


class OllamaProvider:
    name = "ollama"

    def __init__(
        self,
        base_url: str = DEFAULT_BASE_URL,
        transport: httpx.AsyncBaseTransport | None = None,
    ) -> None:
        self._base_url = base_url.rstrip("/")
        self._transport = transport

    async def generate(self, request: ProviderRequest) -> ProviderResponse:
        options: dict[str, Any] = {"num_predict": request.max_tokens}
        if request.temperature is not None:
            options["temperature"] = request.temperature

        payload: dict[str, Any] = {
            "model": request.model,
            "messages": [
                {"role": "system", "content": request.system},
                {"role": "user", "content": request.user},
            ],
            "stream": False,
            "options": options,
        }
        if request.json_schema is not None:
            payload["format"] = request.json_schema

        try:
            async with httpx.AsyncClient(
                base_url=self._base_url,
                timeout=request.timeout_seconds,
                transport=self._transport,
            ) as client:
                response = await client.post("/api/chat", json=payload)
        except httpx.HTTPError as exc:
            raise ProviderError(
                f"ollama request failed: {type(exc).__name__}: {exc}. "
                f"Is `ollama serve` running and reachable at {self._base_url}?"
            ) from exc

        if response.status_code != httpx.codes.OK:
            raise ProviderError(f"ollama returned {response.status_code}: {_detail(response)}")

        body = response.json()
        content = body.get("message", {}).get("content")
        if not content:
            raise ProviderError("ollama returned no message content")

        return ProviderResponse(
            text=content,
            # Ollama omits these on some code paths; absent is 0, not a crash.
            input_tokens=int(body.get("prompt_eval_count") or 0),
            output_tokens=int(body.get("eval_count") or 0),
            model=body.get("model") or request.model,
        )


def _detail(response: httpx.Response) -> str:
    try:
        payload = response.json()
    except ValueError:
        return response.text[:300]
    if isinstance(payload, dict) and "error" in payload:
        return str(payload["error"])[:300]
    return response.text[:300]
