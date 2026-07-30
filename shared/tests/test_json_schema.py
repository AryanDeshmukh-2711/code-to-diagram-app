"""The exported JSON Schema, and the guard that stops it drifting.

The TypeScript types in /web are generated from this file. If the committed
schema can fall out of step with the Python models, the generated types
inherit that staleness and the whole no-drift guarantee is theatre.
"""

import json
from pathlib import Path

from cpm.export_schema import SCHEMA_FILENAME, build_json_schema

REPO_ROOT = Path(__file__).resolve().parents[2]
COMMITTED_SCHEMA = REPO_ROOT / "schemas" / SCHEMA_FILENAME


def test_schema_exposes_every_cpm_collection() -> None:
    properties = build_json_schema()["properties"]
    assert set(properties) == {
        "meta",
        "actors",
        "entities",
        "relationships",
        "useCases",
        "flows",
        "states",
        "components",
        "nodes",
        "requirements",
    }


def test_schema_uses_camel_case_property_names() -> None:
    schema = build_json_schema()
    state = schema["$defs"]["State"]["properties"]
    assert "entityRef" in state
    assert "isInitial" in state
    assert "entity_ref" not in state


def test_schema_uses_the_from_keyword_not_the_python_field_name() -> None:
    schema = build_json_schema()
    assert "from" in schema["$defs"]["Relationship"]["properties"]
    assert "from_" not in schema["$defs"]["Relationship"]["properties"]
    assert "from" in schema["$defs"]["FlowStep"]["properties"]


def test_schema_forbids_additional_properties() -> None:
    schema = build_json_schema()
    assert schema["additionalProperties"] is False
    for name, definition in schema["$defs"].items():
        if definition.get("type") == "object":
            assert definition["additionalProperties"] is False, name


def test_schema_carries_the_slug_pattern_so_generated_clients_see_it() -> None:
    entity_id = build_json_schema()["$defs"]["Entity"]["properties"]["id"]
    assert "pattern" in entity_id


def test_schema_has_no_property_level_titles() -> None:
    # Pydantic titles every single property. json-schema-to-typescript turns each
    # title into its own exported alias, producing Id, Id1, Id2, Name1, Name2...
    # which is unusable as a public type surface.
    schema = build_json_schema()
    for name, definition in schema["$defs"].items():
        for property_name, property_schema in definition.get("properties", {}).items():
            assert "title" not in property_schema, f"{name}.{property_name}"
    for property_name, property_schema in schema["properties"].items():
        assert "title" not in property_schema, f"CPM.{property_name}"


def test_schema_keeps_definition_titles_so_generated_interfaces_are_named() -> None:
    schema = build_json_schema()
    assert schema["title"] == "CPM"
    assert schema["$defs"]["Entity"]["title"] == "Entity"
    assert schema["$defs"]["RelationshipType"]["title"] == "RelationshipType"


def test_schema_generation_is_deterministic() -> None:
    assert json.dumps(build_json_schema(), sort_keys=True) == json.dumps(
        build_json_schema(), sort_keys=True
    )


def test_committed_schema_matches_the_models() -> None:
    assert COMMITTED_SCHEMA.is_file(), f"missing {COMMITTED_SCHEMA}; run `make types`"
    committed = json.loads(COMMITTED_SCHEMA.read_text(encoding="utf-8"))
    assert committed == build_json_schema(), (
        "schemas/cpm.schema.json is stale relative to the Pydantic models. "
        "Run `make types` and commit the result."
    )
