"""Per-task LLM configuration.

Every model identifier in the product lives in cpm-adjacent config, in exactly
one module. These tests lock that down, and lock down that a task cannot be
added without a pricing entry — otherwise cost accounting (NFR-M3/M4) silently
reports nothing for it.
"""

import pytest

from llm.config import TASKS, TaskConfig, get_task
from llm.errors import UnknownTaskError
from llm.pricing import PRICING, estimate_cost_usd


def test_every_declared_task_is_retrievable() -> None:
    for name in TASKS:
        assert isinstance(get_task(name), TaskConfig)


def test_unknown_task_raises_and_lists_the_known_ones() -> None:
    with pytest.raises(UnknownTaskError) as excinfo:
        get_task("no-such-task")
    # A typo should not become a runtime mystery — the error names the options.
    for known in TASKS:
        assert known in str(excinfo.value)


def test_the_cpm_extraction_task_exists() -> None:
    # The one task the whole product depends on: input -> CPM.
    assert "cpm_extraction" in TASKS


def test_every_task_has_a_pricing_entry() -> None:
    # Without this, adding a task with an unpriced model makes its cost vanish
    # from reporting with no error at all. NFR-M4 depends on the opposite.
    for name, task in TASKS.items():
        assert task.model in PRICING, f"task {name!r} uses unpriced model {task.model!r}"


def test_every_task_has_a_system_prompt_and_a_positive_token_budget() -> None:
    for name, task in TASKS.items():
        assert task.system_prompt.strip(), name
        assert task.max_tokens > 0, name
        assert task.timeout_seconds > 0, name


def test_local_models_are_priced_at_zero_not_left_unpriced() -> None:
    # Local inference genuinely costs nothing per token. That must be an
    # explicit 0, not a missing entry — a missing entry is indistinguishable
    # from "we forgot", and the two need different responses.
    #
    # Read through TASKS rather than hardcoding an id: a model literal here
    # would itself violate the no-model-names-outside-the-gateway rule.
    model = TASKS["cpm_extraction"].model
    assert estimate_cost_usd(model, input_tokens=10_000, output_tokens=5_000) == 0


def test_unknown_model_costs_none_rather_than_zero() -> None:
    # Returning 0.0 for an unknown model would under-report spend and look
    # exactly like a free local model. None means "not measured".
    assert estimate_cost_usd("some-unpriced-model", 1000, 1000) is None


def test_priced_model_cost_scales_with_tokens() -> None:
    PRICING["test-priced-model"] = PRICING.get("test-priced-model") or _fake_rate()
    try:
        cheap = estimate_cost_usd("test-priced-model", 1_000, 1_000)
        dear = estimate_cost_usd("test-priced-model", 2_000, 2_000)
        assert cheap is not None and dear is not None
        assert dear == cheap * 2
    finally:
        PRICING.pop("test-priced-model", None)


def _fake_rate():
    from llm.pricing import ModelRate

    return ModelRate(input_usd_per_million="1.00", output_usd_per_million="2.00")


def test_temperature_is_supported_because_open_models_accept_it() -> None:
    # Recorded deliberately: the current Anthropic models reject temperature
    # outright (HTTP 400). Open-weight models do not, which is why the field
    # is usable at all in this configuration.
    task = get_task("cpm_extraction")
    assert task.temperature is None or 0.0 <= task.temperature <= 2.0


def test_extraction_runs_deterministically() -> None:
    # FR-9: identical input should give identical output wherever possible.
    # Sampling temperature above zero on the extraction step works against
    # that directly.
    assert get_task("cpm_extraction").temperature == 0.0
