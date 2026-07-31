"""The run always validates, and there is no way to ask it not to.

Two things are asserted here that a normal behavioural test would not bother
with: that no bypass parameter exists anywhere in the signature or the
codebase, and that the validate call is not sitting inside an `if`. Both are
structural, because the failure mode is not "the code is wrong today" — it is
"someone adds a flag in six weeks and the guarantee dies quietly".
"""

import ast
import inspect
import os
import re
from pathlib import Path

import pytest

from consistency.validator import ConsistencyViolation
from cpm.fixtures import load_library_management_system
from diagrams.mapper import DiagramMapper
from diagrams.registry import registry
from diagrams.renderer import DiagramRenderer
from diagrams.types import RenderFormat
from generation import run as run_module
from generation.run import execute_generation_run

SVG = b"<svg xmlns='http://www.w3.org/2000/svg'></svg>"


class AlwaysRenders:
    def __init__(self, name: str) -> None:
        self.name = name

    async def render(self, source: str, fmt: RenderFormat) -> bytes:
        return SVG


class AlwaysFails:
    def __init__(self, name: str) -> None:
        self.name = name

    async def render(self, source: str, fmt: RenderFormat) -> bytes:
        from diagrams.engines.base import EngineUnavailable

        raise EngineUnavailable("engine is down")


@pytest.fixture(scope="module")
def cpm():
    return load_library_management_system()


def engines(ok: bool = True):
    factory = AlwaysRenders if ok else AlwaysFails
    return {"plantuml": factory("plantuml"), "mermaid": factory("mermaid")}


def corrupting_mapper(diagram_type: str, before: str, after: str) -> DiagramMapper:
    """A mapper that emits a drifted name — the bug the validator exists for."""
    original = registry()[diagram_type]

    def to_source(cpm):
        return original.to_source(cpm).replace(before, after)

    return DiagramMapper(
        diagram_type=original.diagram_type,
        title=original.title,
        engine=original.engine,
        to_source=to_source,
    )


# --------------------------------------------------------------------------
# Behaviour
# --------------------------------------------------------------------------


async def test_a_clean_run_succeeds_and_reports_what_it_checked(cpm) -> None:
    result = await execute_generation_run(cpm, DiagramRenderer(engines=engines()))

    from diagrams.registry import registered_types

    assert result.consistency.ok
    assert result.consistency.recognised_names > 0
    assert len(result.rendered) == len(registered_types())
    assert result.failed == []


async def test_a_corrupted_mapper_fails_the_whole_run(cpm) -> None:
    mappers = {**registry(), "class": corrupting_mapper("class", '"Book"', '"Books"')}
    renderer = DiagramRenderer(engines=engines(), mappers=mappers)

    with pytest.raises(ConsistencyViolation) as excinfo:
        await execute_generation_run(cpm, renderer)

    message = str(excinfo.value)
    assert "class" in message
    assert "'Book'" in message and "'Books'" in message


async def test_the_run_fails_even_though_every_diagram_rendered_fine(cpm) -> None:
    # This is the distinction that matters: rendering succeeded, so nothing
    # downstream would have noticed. The set is internally inconsistent and
    # that alone must stop it.
    mappers = {**registry(), "use_case": corrupting_mapper("use_case", '"Member"', '"Members"')}

    with pytest.raises(ConsistencyViolation):
        await execute_generation_run(cpm, DiagramRenderer(engines=engines(), mappers=mappers))


async def test_a_render_failure_does_not_fail_the_run(cpm) -> None:
    # The deliberate asymmetry with FR-11: a diagram that could not be drawn
    # costs the user that diagram; a diagram that contradicts the model costs
    # them the run.
    renderer = DiagramRenderer(
        engines={"plantuml": AlwaysRenders("plantuml"), "mermaid": AlwaysFails("mermaid")}
    )
    result = await execute_generation_run(cpm, renderer)
    from diagrams.registry import registry

    mermaid_types = [t for t, m in registry().items() if str(m.engine) == "mermaid"]

    assert result.consistency.ok
    assert len(result.failed) == len(mermaid_types)
    assert len(result.rendered) == len(registry()) - len(mermaid_types)


# --------------------------------------------------------------------------
# No bypass
# --------------------------------------------------------------------------

BYPASS_NAMES = re.compile(
    r"skip[_-]?validation|skip[_-]?consistency|no[_-]?validate|"
    r"disable[_-]?validation|disable[_-]?consistency|bypass[_-]?validation|"
    r"ignore[_-]?consistency|consistency[_-]?enabled|"
    r"validate\s*=\s*(?:False|0|None)",
    re.IGNORECASE,
)
"""Deliberately does not include a bare "validate_consistency" pattern: with
IGNORECASE that matches the validator's own function name, and a guardrail that
flags the thing it protects gets deleted rather than fixed."""


def test_the_run_signature_has_no_way_to_turn_validation_off() -> None:
    parameters = set(inspect.signature(execute_generation_run).parameters)
    assert not any(BYPASS_NAMES.search(name) for name in parameters), parameters


def test_the_validate_call_is_not_inside_a_conditional() -> None:
    # A flag is the obvious bypass; a quiet `if settings.strict:` is the one
    # that gets added without anyone calling it a bypass.
    tree = ast.parse(Path(run_module.__file__).read_text(encoding="utf-8"))

    def calls_validate(node: ast.AST) -> bool:
        return any(
            isinstance(inner, ast.Call)
            and isinstance(inner.func, ast.Name)
            and inner.func.id == "validate_consistency"
            for inner in ast.walk(node)
        )

    guarded = [node for node in ast.walk(tree) if isinstance(node, ast.If) and calls_validate(node)]
    assert not guarded, "validate_consistency is reachable only conditionally"
    assert calls_validate(tree), "validate_consistency is not called at all"


def test_no_bypass_switch_exists_anywhere_in_the_codebase() -> None:
    # Same scan root as the no-hardcoded-models guardrail. Deriving it from
    # this module's location instead would scan /srv, which holds both the
    # installed package and the read-only repo mount — every file twice, under
    # two paths, so excluding this file by path would silently miss its twin.
    repo_root = Path(os.environ.get("ASA_REPO_ROOT", Path(run_module.__file__).parents[2]))
    skipped = {
        ".git",
        "node_modules",
        ".next",
        "__pycache__",
        ".venv",
        ".ruff_cache",
        ".pytest_cache",
    }
    this_file = Path(__file__).name

    offenders = []
    for path in repo_root.rglob("*.py"):
        if any(part in skipped for part in path.parts) or path.name == this_file:
            continue
        for number, line in enumerate(path.read_text(encoding="utf-8").splitlines(), start=1):
            if BYPASS_NAMES.search(line):
                offenders.append(
                    f"{path.relative_to(repo_root).as_posix()}:{number}: {line.strip()}"
                )

    assert not offenders, "a validation bypass appeared:\n" + "\n".join(offenders)


def test_the_bypass_scanner_would_catch_a_planted_flag(tmp_path: Path) -> None:
    # Otherwise the check above passes because the pattern matches nothing.
    planted = tmp_path / "sneaky.py"
    planted.write_text("def run(cpm, skip_validation: bool = False): ...\n", encoding="utf-8")
    assert BYPASS_NAMES.search(planted.read_text(encoding="utf-8"))


def test_validation_runs_before_the_result_is_constructible() -> None:
    # The result type carries the report, so a run object cannot exist without
    # one having been produced.
    from generation.run import GenerationRunResult

    assert "consistency" in inspect.signature(GenerationRunResult).parameters
