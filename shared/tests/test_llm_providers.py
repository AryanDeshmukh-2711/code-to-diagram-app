"""Provider adapters.

Driven through httpx.MockTransport: the wire shape is asserted exactly, and no
test touches the network. Two adapters cover every free option worth having —
Ollama for local inference, and one OpenAI-compatible adapter that serves Groq,
OpenRouter, Together, LM Studio and vLLM, because they all speak the same
Chat Completions dialect.
"""

import json

import httpx
import pytest

from llm.errors import ProviderError
from llm.providers.base import ProviderRequest
from llm.providers.ollama import OllamaProvider
from llm.providers.openai_compatible import OpenAICompatibleProvider

SCHEMA = {
    "type": "object",
    "properties": {"name": {"type": "string"}, "count": {"type": "integer"}},
    "required": ["name", "count"],
    "additionalProperties": False,
}

REQUEST = ProviderRequest(
    model="test-model",
    system="You extract things.",
    user="some untrusted text",
    json_schema=SCHEMA,
    max_tokens=512,
    temperature=0.0,
    timeout_seconds=30.0,
)


def transport_capturing(payload: dict, captured: list[httpx.Request]) -> httpx.MockTransport:
    def handler(request: httpx.Request) -> httpx.Response:
        captured.append(request)
        return httpx.Response(200, json=payload)

    return httpx.MockTransport(handler)


# --------------------------------------------------------------------------
# Ollama
# --------------------------------------------------------------------------

OLLAMA_OK = {
    "model": "test-model",
    "message": {"role": "assistant", "content": '{"name": "Book", "count": 3}'},
    "done": True,
    "prompt_eval_count": 210,
    "eval_count": 34,
}


async def test_ollama_returns_text_and_token_counts() -> None:
    captured: list[httpx.Request] = []
    provider = OllamaProvider(
        base_url="http://ollama:11434", transport=transport_capturing(OLLAMA_OK, captured)
    )
    response = await provider.generate(REQUEST)

    assert response.text == '{"name": "Book", "count": 3}'
    assert response.input_tokens == 210
    assert response.output_tokens == 34
    assert response.model == "test-model"


async def test_ollama_posts_to_the_chat_endpoint_without_streaming() -> None:
    captured: list[httpx.Request] = []
    provider = OllamaProvider(
        base_url="http://ollama:11434", transport=transport_capturing(OLLAMA_OK, captured)
    )
    await provider.generate(REQUEST)

    assert captured[0].url.path == "/api/chat"
    body = json.loads(captured[0].content)
    assert body["stream"] is False, "streaming would break the single-shot contract"
    assert body["model"] == "test-model"


async def test_ollama_sends_system_and_user_as_separate_roles() -> None:
    captured: list[httpx.Request] = []
    provider = OllamaProvider(
        base_url="http://ollama:11434", transport=transport_capturing(OLLAMA_OK, captured)
    )
    await provider.generate(REQUEST)

    messages = json.loads(captured[0].content)["messages"]
    assert [m["role"] for m in messages] == ["system", "user"]
    assert messages[0]["content"] == "You extract things."
    assert messages[1]["content"] == "some untrusted text"


async def test_ollama_passes_the_schema_as_the_format_constraint() -> None:
    # Ollama constrains decoding to the schema. That is what makes structured
    # output a guarantee rather than a request.
    captured: list[httpx.Request] = []
    provider = OllamaProvider(
        base_url="http://ollama:11434", transport=transport_capturing(OLLAMA_OK, captured)
    )
    await provider.generate(REQUEST)

    assert json.loads(captured[0].content)["format"] == SCHEMA


async def test_ollama_maps_temperature_and_token_budget_into_options() -> None:
    captured: list[httpx.Request] = []
    provider = OllamaProvider(
        base_url="http://ollama:11434", transport=transport_capturing(OLLAMA_OK, captured)
    )
    await provider.generate(REQUEST)

    options = json.loads(captured[0].content)["options"]
    assert options["temperature"] == 0.0
    assert options["num_predict"] == 512


async def test_ollama_raises_a_typed_error_on_http_failure() -> None:
    transport = httpx.MockTransport(lambda _: httpx.Response(500, text="model not loaded"))
    provider = OllamaProvider(base_url="http://ollama:11434", transport=transport)

    with pytest.raises(ProviderError) as excinfo:
        await provider.generate(REQUEST)
    assert "500" in str(excinfo.value)


async def test_ollama_reports_a_missing_model_as_a_provider_error() -> None:
    # The most common first-run failure: the model was never pulled. It must
    # not surface as a schema-validation problem.
    transport = httpx.MockTransport(
        lambda _: httpx.Response(
            404, json={"error": 'model "test-model" not found, try pulling it'}
        )
    )
    provider = OllamaProvider(base_url="http://ollama:11434", transport=transport)

    with pytest.raises(ProviderError, match="not found"):
        await provider.generate(REQUEST)


# --------------------------------------------------------------------------
# OpenAI-compatible (Groq / OpenRouter / Together / LM Studio / vLLM)
# --------------------------------------------------------------------------

OPENAI_OK = {
    "model": "test-model",
    "choices": [{"message": {"role": "assistant", "content": '{"name": "Book", "count": 3}'}}],
    "usage": {"prompt_tokens": 210, "completion_tokens": 34},
}


async def test_openai_compatible_returns_text_and_token_counts() -> None:
    captured: list[httpx.Request] = []
    provider = OpenAICompatibleProvider(
        base_url="https://example.invalid/v1",
        api_key="secret",
        transport=transport_capturing(OPENAI_OK, captured),
    )
    response = await provider.generate(REQUEST)

    assert response.text == '{"name": "Book", "count": 3}'
    assert response.input_tokens == 210
    assert response.output_tokens == 34


async def test_openai_compatible_posts_to_chat_completions_with_bearer_auth() -> None:
    captured: list[httpx.Request] = []
    provider = OpenAICompatibleProvider(
        base_url="https://example.invalid/v1",
        api_key="secret",
        transport=transport_capturing(OPENAI_OK, captured),
    )
    await provider.generate(REQUEST)

    assert captured[0].url.path.endswith("/chat/completions")
    assert captured[0].headers["authorization"] == "Bearer secret"


async def test_openai_compatible_requests_a_json_schema_response_format() -> None:
    captured: list[httpx.Request] = []
    provider = OpenAICompatibleProvider(
        base_url="https://example.invalid/v1",
        api_key="secret",
        transport=transport_capturing(OPENAI_OK, captured),
    )
    await provider.generate(REQUEST)

    response_format = json.loads(captured[0].content)["response_format"]
    assert response_format["type"] == "json_schema"
    assert response_format["json_schema"]["schema"] == SCHEMA
    assert response_format["json_schema"]["strict"] is True


async def test_openai_compatible_works_without_an_api_key() -> None:
    # LM Studio and a local vLLM serve the same dialect with no auth at all.
    captured: list[httpx.Request] = []
    provider = OpenAICompatibleProvider(
        base_url="http://localhost:1234/v1",
        api_key=None,
        transport=transport_capturing(OPENAI_OK, captured),
    )
    await provider.generate(REQUEST)
    assert "authorization" not in captured[0].headers


async def test_openai_compatible_raises_a_typed_error_on_http_failure() -> None:
    transport = httpx.MockTransport(lambda _: httpx.Response(429, text="rate limited"))
    provider = OpenAICompatibleProvider(
        base_url="https://example.invalid/v1", api_key="k", transport=transport
    )
    with pytest.raises(ProviderError, match="429"):
        await provider.generate(REQUEST)


async def test_openai_compatible_raises_when_the_response_has_no_choices() -> None:
    transport = httpx.MockTransport(lambda _: httpx.Response(200, json={"choices": []}))
    provider = OpenAICompatibleProvider(
        base_url="https://example.invalid/v1", api_key="k", transport=transport
    )
    with pytest.raises(ProviderError):
        await provider.generate(REQUEST)


async def test_an_api_key_never_appears_in_an_error_message() -> None:
    # Provider errors get logged and surfaced; a key in the text would leak
    # into logs and, via a failed generation run, potentially to a user.
    transport = httpx.MockTransport(lambda _: httpx.Response(401, text="bad key"))
    provider = OpenAICompatibleProvider(
        base_url="https://example.invalid/v1",
        api_key="super-secret-key",
        transport=transport,
    )
    with pytest.raises(ProviderError) as excinfo:
        await provider.generate(REQUEST)
    assert "super-secret-key" not in str(excinfo.value)
