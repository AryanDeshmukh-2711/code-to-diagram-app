"""Regenerate the golden diagram sources. Run via `make golden`.

Golden files are committed so a change to a mapper shows up as a reviewable
diff rather than as a silently different diagram. Regenerating is a deliberate
act: run this, read the diff, then commit it.
"""

from pathlib import Path

from cpm.fixtures import load_library_management_system
from diagrams.registry import registry

GOLDEN_DIR = Path(__file__).resolve().parent / "golden"
EXTENSION = {"plantuml": "puml", "mermaid": "mmd"}


def main() -> None:
    GOLDEN_DIR.mkdir(parents=True, exist_ok=True)
    cpm = load_library_management_system()

    for diagram_type, mapper in sorted(registry().items()):
        path = GOLDEN_DIR / f"{diagram_type}.{EXTENSION[str(mapper.engine)]}"
        source = mapper.to_source(cpm)
        changed = not path.exists() or path.read_text(encoding="utf-8") != source
        path.write_text(source, encoding="utf-8", newline="\n")
        print(f"{'updated' if changed else 'unchanged'}  {path.name}  ({len(source)} bytes)")


if __name__ == "__main__":
    main()
