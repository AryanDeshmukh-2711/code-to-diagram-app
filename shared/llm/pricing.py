"""Per-model token rates, and the cost of one call.

NFR-M3 requires per-run cost attributable to a user; NFR-M4 requires that cost
stay under a fraction of tier revenue. Neither is possible without measuring,
so every call records tokens, and cost wherever a rate is known.

Local inference is priced at an explicit **zero**, not left absent. Zero and
"unmeasured" are different states and need different responses: zero is a fact,
absent is a bug. An unknown model therefore returns None and logs a warning
rather than quietly contributing 0.00 to a spend report.
"""

import logging
from dataclasses import dataclass
from decimal import Decimal

logger = logging.getLogger(__name__)

_PER_MILLION = Decimal(1_000_000)


@dataclass(frozen=True)
class ModelRate:
    """USD per million tokens. Strings, so Decimal parses them exactly."""

    input_usd_per_million: str
    output_usd_per_million: str
    note: str = ""


# Local models served by Ollama. Free at the margin — the cost is electricity
# and the GPU you already own, neither of which is per-token.
_LOCAL = ModelRate("0", "0", note="local inference; no per-token cost")

PRICING: dict[str, ModelRate] = {
    "qwen2.5:7b": _LOCAL,
    "qwen2.5:14b": _LOCAL,
    "qwen2.5-coder:7b": _LOCAL,
    "llama3.1:8b": _LOCAL,
    "mistral-nemo:12b": _LOCAL,
    "gemma2:9b": _LOCAL,
    "phi4:14b": _LOCAL,
}
"""Rates by model id.

Hosted providers are deliberately absent. Adding one means adding its published
rate here — and until you do, its cost reports as None with a warning rather
than as free, which is the honest default for a table nobody has filled in.
"""


def estimate_cost_usd(model: str, input_tokens: int, output_tokens: int) -> Decimal | None:
    """Cost of one call, or None when the model has no rate on file."""
    rate = PRICING.get(model)
    if rate is None:
        logger.warning(
            "no pricing entry for model %r; cost will be recorded as unmeasured, not as zero",
            model,
        )
        return None

    return (
        Decimal(rate.input_usd_per_million) * input_tokens
        + Decimal(rate.output_usd_per_million) * output_tokens
    ) / _PER_MILLION
