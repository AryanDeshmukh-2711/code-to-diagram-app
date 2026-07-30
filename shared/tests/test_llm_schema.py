"""Wire-safe JSON Schema generation.

The CPM carries `pattern` on every id and length bounds on every name.
Constrained decoders reject those keywords, so they are stripped on the way
out — and re-applied by Pydantic on the way back in. These tests pin both
halves of that bargain.
"""

from typing import Annotated

import pytest
from pydantic import BaseModel, ConfigDict, StringConstraints, ValidationError

from llm.schema import to_response_schema

Slugish = Annotated[str, StringConstraints(pattern=r"^[a-z-]+$", min_length=1, max_length=10)]


class Thing(BaseModel):
    model_config = ConfigDict(extra="forbid")

    id: Slugish
    name: str


def test_unsupported_constraints_are_stripped_from_the_wire_schema() -> None:
    properties = to_response_schema(Thing)["properties"]
    assert "pattern" not in properties["id"]
    assert "minLength" not in properties["id"]
    assert "maxLength" not in properties["id"]


def test_the_shape_survives_stripping() -> None:
    schema = to_response_schema(Thing)
    assert set(schema["properties"]) == {"id", "name"}
    assert schema["required"] == ["id", "name"]
    assert schema["additionalProperties"] is False


def test_stripped_constraints_are_still_enforced_by_pydantic() -> None:
    # This is the whole justification for stripping: the wire schema shapes
    # decoding, Pydantic remains the judge. If this ever stopped holding, the
    # gateway would be handing back ids that violate the CPM's own id rules.
    with pytest.raises(ValidationError):
        Thing.model_validate({"id": "NOT A SLUG", "name": "x"})


def test_the_real_cpm_schema_can_be_sent_over_the_wire() -> None:
    from cpm.schema import CPM

    schema = to_response_schema(CPM)
    assert "pattern" not in _flatten_keywords(schema)


def _flatten_keywords(node, found=None) -> set[str]:
    found = set() if found is None else found
    if isinstance(node, dict):
        found.update(node.keys())
        for value in node.values():
            _flatten_keywords(value, found)
    elif isinstance(node, list):
        for item in node:
            _flatten_keywords(item, found)
    return found
