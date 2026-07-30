"""Guardrail: no LLM anywhere in the render path.

One model call inside a mapper destroys FR-9 and FR-10 at the same time — two
renders of the same CPM could disagree with each other and with the SRS prose,
and the consistency validator would be checking output that was never
deterministic to begin with. It is also the single easiest shortcut to take
while debugging ("just ask the model to fix the layout"), which is exactly why
it is asserted rather than trusted.
"""

import ast
import inspect
from pathlib import Path

import pytest

from diagrams import mappers as mappers_package
from diagrams.registry import registry as mapper_registry

MAPPERS_DIR = Path(mappers_package.__file__).resolve().parent
DIAGRAMS_DIR = MAPPERS_DIR.parent

FORBIDDEN_MODULES = {"llm", "anthropic", "openai", "ollama", "groq", "httpx", "requests"}
"""No network client either: a mapper that fetched anything would stop being a
pure function of the CPM. Engines legitimately use httpx, so this applies to
mappers only."""


def _mapper_modules() -> list[Path]:
    return sorted(p for p in MAPPERS_DIR.glob("*.py") if p.name != "__init__.py")


def _imported_roots(tree: ast.AST) -> set[str]:
    roots: set[str] = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            roots.update(alias.name.split(".")[0] for alias in node.names)
        elif isinstance(node, ast.ImportFrom) and node.module:
            roots.add(node.module.split(".")[0])
    return roots


def test_there_are_mapper_modules_to_check() -> None:
    # A guardrail over an empty set passes forever.
    assert _mapper_modules()


@pytest.mark.parametrize("path", _mapper_modules(), ids=lambda p: p.name)
def test_a_mapper_imports_no_model_client(path: Path) -> None:
    tree = ast.parse(path.read_text(encoding="utf-8"))
    offending = _imported_roots(tree) & FORBIDDEN_MODULES
    assert not offending, f"{path.name} imports {', '.join(sorted(offending))}"


@pytest.mark.parametrize("path", _mapper_modules(), ids=lambda p: p.name)
def test_a_mapper_contains_no_async_code(path: Path) -> None:
    # Purity in the shape that matters: a mapper that could await could do I/O.
    tree = ast.parse(path.read_text(encoding="utf-8"))
    for node in ast.walk(tree):
        assert not isinstance(node, ast.AsyncFunctionDef), f"{path.name} defines an async function"
        assert not isinstance(node, ast.Await), f"{path.name} contains an await"


def test_no_registered_mapper_is_a_coroutine_function() -> None:
    for diagram_type, mapper in mapper_registry().items():
        assert not inspect.iscoroutinefunction(mapper.to_source), diagram_type


def test_the_diagrams_package_never_imports_the_llm_gateway() -> None:
    # Engines may use httpx; nothing in the package may reach for a model.
    offenders = []
    for path in DIAGRAMS_DIR.rglob("*.py"):
        roots = _imported_roots(ast.parse(path.read_text(encoding="utf-8")))
        if roots & {"llm", "anthropic", "openai", "ollama", "groq"}:
            offenders.append(path.relative_to(DIAGRAMS_DIR).as_posix())
    assert not offenders, f"LLM access inside the render path: {offenders}"


def test_the_detector_would_catch_a_planted_import(tmp_path: Path) -> None:
    # Proves the AST walk actually matches, rather than the suite passing
    # because nothing is ever detected.
    planted = tmp_path / "sneaky.py"
    planted.write_text("from llm.gateway import LLMGateway\n", encoding="utf-8")
    assert _imported_roots(ast.parse(planted.read_text(encoding="utf-8"))) & FORBIDDEN_MODULES
