"""Export the CPM JSON Schema, the contract the TypeScript types are generated from.

Run as a module:

    python -m cpm.export_schema ../schemas/cpm.schema.json
    python -m cpm.export_schema ../schemas/cpm.schema.json --check

``--check`` exits non-zero when the committed file no longer matches the models.
That check is what makes the generated TypeScript unable to drift: the schema
cannot go stale silently, and the TS is regenerated from the schema.
"""

import argparse
import json
from pathlib import Path
from typing import Any

SCHEMA_FILENAME = "cpm.schema.json"
JSON_SCHEMA_DIALECT = "https://json-schema.org/draft/2020-12/schema"


def _strip_titles(node: Any) -> None:
    """Recursively drop every ``title``, skipping the ``$defs`` container."""
    if isinstance(node, dict):
        node.pop("title", None)
        for key, value in node.items():
            if key == "$defs":
                continue
            _strip_titles(value)
    elif isinstance(node, list):
        for item in node:
            _strip_titles(item)


def build_json_schema() -> dict[str, Any]:
    """The CPM JSON Schema, with camelCase property names.

    Pydantic titles every property, and json-schema-to-typescript promotes each
    title to its own exported alias — yielding Id, Id1, Name2 and so on. So the
    titles are stripped everywhere except the root and the top level of each
    definition, which are the ones that name the generated interfaces.
    """
    from cpm.schema import CPM

    schema: dict[str, Any] = CPM.model_json_schema(by_alias=True)

    definition_titles = {
        name: definition.get("title") for name, definition in schema.get("$defs", {}).items()
    }
    for name, definition in schema.get("$defs", {}).items():
        _strip_titles(definition)
        if definition_titles[name] is not None:
            definition["title"] = definition_titles[name]

    root_title = schema.get("title")
    _strip_titles(schema)
    if root_title is not None:
        schema["title"] = root_title

    schema["$schema"] = JSON_SCHEMA_DIALECT
    return schema


def render() -> str:
    """The schema as it should appear on disk: sorted, indented, one trailing newline."""
    return json.dumps(build_json_schema(), indent=2, sort_keys=True) + "\n"


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("output", type=Path, help="path to write (or verify)")
    parser.add_argument(
        "--check",
        action="store_true",
        help="verify the file matches the models instead of writing it",
    )
    args = parser.parse_args(argv)

    expected = build_json_schema()

    if args.check:
        if not args.output.is_file():
            print(f"missing {args.output}; run `make types`")
            return 1
        # Compared as parsed JSON, not raw text, so a CRLF checkout cannot
        # produce a spurious failure.
        if json.loads(args.output.read_text(encoding="utf-8")) != expected:
            print(f"{args.output} is stale relative to the Pydantic models; run `make types`")
            return 1
        print(f"{args.output} is up to date")
        return 0

    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(render(), encoding="utf-8", newline="\n")
    print(f"wrote {args.output}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
