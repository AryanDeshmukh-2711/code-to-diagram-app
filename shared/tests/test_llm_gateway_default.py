"""build_default_gateway's api_key_override — the BYO-key handoff point.

Provider, base URL and model stay whatever the operator configured via env
vars; only the bearer credential is allowed to vary per caller. These tests
cover that boundary directly, without going through LLMGateway.complete()'s
task resolution (which reads llm.config.TASKS, bound at import time from
LLM_PROVIDER — not something a per-test env var can retarget).
"""

from llm.gateway import build_default_gateway


def test_no_openai_base_url_means_no_openai_compatible_provider_at_all(monkeypatch) -> None:
    monkeypatch.delenv("LLM_OPENAI_BASE_URL", raising=False)
    monkeypatch.delenv("LLM_API_KEY", raising=False)

    gateway = build_default_gateway(api_key_override="visitor-key")

    assert "openai_compatible" not in gateway._providers
    assert "ollama" in gateway._providers


def test_override_takes_precedence_over_the_env_var_key(monkeypatch) -> None:
    monkeypatch.setenv("LLM_OPENAI_BASE_URL", "https://api.groq.com/openai/v1")
    monkeypatch.setenv("LLM_API_KEY", "server-configured-key")

    gateway = build_default_gateway(api_key_override="visitor-key")

    provider = gateway._providers["openai_compatible"]
    assert provider._api_key == "visitor-key"


def test_no_override_falls_back_to_the_env_var_key(monkeypatch) -> None:
    monkeypatch.setenv("LLM_OPENAI_BASE_URL", "https://api.groq.com/openai/v1")
    monkeypatch.setenv("LLM_API_KEY", "server-configured-key")

    gateway = build_default_gateway()

    provider = gateway._providers["openai_compatible"]
    assert provider._api_key == "server-configured-key"


def test_no_override_and_no_env_key_leaves_it_unset(monkeypatch) -> None:
    # The local-server case: an OpenAI-compatible endpoint (LM Studio, vLLM)
    # that needs no key at all.
    monkeypatch.setenv("LLM_OPENAI_BASE_URL", "http://localhost:1234/v1")
    monkeypatch.delenv("LLM_API_KEY", raising=False)

    gateway = build_default_gateway()

    provider = gateway._providers["openai_compatible"]
    assert provider._api_key is None
