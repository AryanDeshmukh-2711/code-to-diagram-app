"""One adapter for every backend that speaks OpenAI Chat Completions.

Groq, OpenRouter, Together, Cerebras, LM Studio and a local vLLM all expose the
same dialect, so they are one adapter and a base URL rather than five adapters.
Point it at whichever free tier you want; `api_key` is optional because local
servers do not use one.

Note the tradeoff before reaching for a hosted free tier: most of them train on
submitted content by default, which conflicts with SRS §6.3 and §9.2. Local
inference (see `ollama.py`) does not have that problem.
"""

import logging
from typing import Any

import httpx

from llm.errors import ProviderError
from llm.providers.base import ProviderRequest, ProviderResponse

logger = logging.getLogger(__name__)


class OpenAICompatibleProvider:
    name = "openai_compatible"

    def __init__(
        self,
        base_url: str,
        api_key: str | None = None,
        transport: httpx.AsyncBaseTransport | None = None,
    ) -> None:
        self._base_url = base_url.rstrip("/")
        self._api_key = api_key
        self._transport = transport

    async def generate(self, request: ProviderRequest) -> ProviderResponse:
        payload: dict[str, Any] = {
            "model": request.model,
            "messages": [
                {"role": "system", "content": request.system},
                {"role": "user", "content": request.user},
            ],
            "max_tokens": request.max_tokens,
            "stream": False,
        }
        if request.temperature is not None:
            payload["temperature"] = request.temperature
        if request.json_schema is not None:
            payload["response_format"] = {
                "type": "json_schema",
                "json_schema": {
                    "name": "structured_output",
                    "schema": request.json_schema,
                    "strict": True,
                },
            }

        headers = {}
        if self._api_key:
            headers["Authorization"] = f"Bearer {self._api_key}"

        try:
            async with httpx.AsyncClient(
                base_url=self._base_url,
                timeout=request.timeout_seconds,
                transport=self._transport,
            ) as client:
                response = await client.post("/chat/completions", json=payload, headers=headers)
        except httpx.HTTPError as exc:
            raise ProviderError(
                f"request to {self._base_url} failed: {type(exc).__name__}: {exc}"
            ) from exc

        if response.status_code != httpx.codes.OK:
            # Body only — never the request headers, which carry the bearer token.
            raise ProviderError(f"provider returned {response.status_code}: {response.text[:300]}")

        body = response.json()
        choices = body.get("choices") or []
        if not choices:
            raise ProviderError("provider returned no choices")

        content = choices[0].get("message", {}).get("content")
        if not content:
            raise ProviderError("provider returned an empty message")

        usage = body.get("usage") or {}
        return ProviderResponse(
            text=content,
            input_tokens=int(usage.get("prompt_tokens") or 0),
            output_tokens=int(usage.get("completion_tokens") or 0),
            model=body.get("model") or request.model,
        )
