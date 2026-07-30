"""Turning a Pydantic model into a schema a constrained decoder will accept.

Structured-output implementations support only a subset of JSON Schema. String
and numeric constraints (`pattern`, `minLength`, `maxLength`, `minimum`, …) are
commonly rejected outright — and the CPM schema is full of them, because a Slug
carries a pattern and every name carries a length bound.

So they are stripped from the schema sent over the wire. **They are not
dropped**: the response is validated with the original Pydantic model, which
re-applies every one of them. The wire schema shapes the decoding; Pydantic
remains the judge of whether the result is acceptable.
"""

from typing import Any

from pydantic import BaseModel

UNSUPPORTED_KEYWORDS = frozenset(
    {
        "pattern",
        "minLength",
        "maxLength",
        "minimum",
        "maximum",
        "exclusiveMinimum",
        "exclusiveMaximum",
        "multipleOf",
        "minItems",
        "maxItems",
        "uniqueItems",
        "format",
    }
)


def _sanitise(node: Any) -> Any:
    if isinstance(node, dict):
        cleaned = {
            key: _sanitise(value) for key, value in node.items() if key not in UNSUPPORTED_KEYWORDS
        }
        # Constrained decoders need to know the object is closed; Pydantic's
        # extra="forbid" already implies it, but not every model sets it.
        if cleaned.get("type") == "object" and "additionalProperties" not in cleaned:
            cleaned["additionalProperties"] = False
        return cleaned
    if isinstance(node, list):
        return [_sanitise(item) for item in node]
    return node


def to_response_schema(model: type[BaseModel]) -> dict[str, Any]:
    """A wire-safe JSON Schema for ``model``."""
    return _sanitise(model.model_json_schema(by_alias=True))
