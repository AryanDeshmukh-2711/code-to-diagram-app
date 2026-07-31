"""Rendering: retry once, then fail without taking the run down.

The property under test is containment. A run produces eight artefacts; one of
them failing must cost the user that one diagram, not the whole three-minute
generation (FR-11, NFR-R2).
"""

from collections import Counter

import pytest

from cpm.fixtures import load_library_management_system
from diagrams.engines.base import EngineError, EngineUnavailable
from diagrams.mapper import DiagramMapper
from diagrams.renderer import MAX_ATTEMPTS, DiagramRenderer
from diagrams.types import Engine, FailedDiagram, RenderedDiagram, RenderFormat

SVG = b"<svg xmlns='http://www.w3.org/2000/svg'></svg>"


class FakeEngine:
    """Scripted engine. Each item is bytes to return or an exception to raise."""

    def __init__(self, name: str, script: list) -> None:
        self.name = name
        self._script = list(script)
        self.calls: list[tuple[str, RenderFormat]] = []

    async def render(self, source: str, fmt: RenderFormat) -> bytes:
        self.calls.append((source, fmt))
        item = self._script.pop(0) if self._script else SVG
        if isinstance(item, BaseException):
            raise item
        return item


@pytest.fixture(scope="module")
def cpm():
    return load_library_management_system()


def renderer(script_by_engine: dict[str, list]) -> tuple[DiagramRenderer, dict[str, FakeEngine]]:
    engines = {name: FakeEngine(name, script) for name, script in script_by_engine.items()}
    return DiagramRenderer(engines=engines), engines


# --------------------------------------------------------------------------
# The happy path
# --------------------------------------------------------------------------


async def test_a_successful_render_carries_its_source_and_bytes(cpm) -> None:
    render, _ = renderer({"plantuml": [SVG], "mermaid": [SVG]})
    result = await render.render(cpm, "class")

    assert isinstance(result, RenderedDiagram)
    assert result.diagram_type == "class"
    assert result.title == "Class Diagram"
    assert result.content == SVG
    assert result.source.startswith("@startuml")
    assert result.ok


async def test_each_diagram_reaches_the_engine_its_mapper_declared(cpm) -> None:
    # Counts come from the registry, not a literal: a new mapper must not make
    # this test fail for the wrong reason.
    from diagrams.registry import registry

    expected = Counter(str(mapper.engine) for mapper in registry().values())

    render, engines = renderer({"plantuml": [], "mermaid": []})
    await render.render_all(cpm)

    for engine_name, count in expected.items():
        assert len(engines[engine_name].calls) == count, engine_name


async def test_render_all_covers_every_registered_type(cpm) -> None:
    from diagrams.registry import registered_types

    render, _ = renderer({"plantuml": [], "mermaid": []})
    results = await render.render_all(cpm)
    assert {r.diagram_type for r in results} == set(registered_types())


# --------------------------------------------------------------------------
# Retry once, then stop
# --------------------------------------------------------------------------


async def test_a_transient_failure_is_retried_and_succeeds(cpm) -> None:
    render, engines = renderer({"plantuml": [EngineUnavailable("connection reset"), SVG]})
    result = await render.render(cpm, "class")

    assert isinstance(result, RenderedDiagram)
    assert len(engines["plantuml"].calls) == 2


async def test_it_retries_exactly_once_then_gives_up(cpm) -> None:
    # Rendering is deterministic, so a third attempt on the same source would
    # only burn time — the retry is for transient engine trouble.
    render, engines = renderer({"plantuml": [EngineError("syntax"), EngineError("syntax")]})
    result = await render.render(cpm, "class")

    assert isinstance(result, FailedDiagram)
    assert len(engines["plantuml"].calls) == MAX_ATTEMPTS == 2
    assert result.attempts == 2


async def test_a_failed_diagram_keeps_the_source_that_failed(cpm) -> None:
    # Otherwise diagnosing it means reproducing the whole run.
    render, _ = renderer({"plantuml": [EngineError("Syntax Error at line 4")] * 2})
    result = await render.render(cpm, "class")

    assert isinstance(result, FailedDiagram)
    assert result.source.startswith("@startuml")
    assert "Syntax Error at line 4" in result.error
    assert not result.ok


# --------------------------------------------------------------------------
# Containment — the DoD property
# --------------------------------------------------------------------------


async def test_one_engine_being_down_does_not_stop_the_others(cpm) -> None:
    render, _ = renderer(
        {
            "plantuml": [SVG, SVG],
            "mermaid": [EngineUnavailable("kroki is not running")] * 2,
        }
    )
    results = {r.diagram_type: r for r in await render.render_all(cpm)}

    assert isinstance(results["entity_relationship"], FailedDiagram)
    assert isinstance(results["class"], RenderedDiagram)
    assert isinstance(results["use_case"], RenderedDiagram)


async def test_a_missing_engine_registration_fails_only_that_diagram(cpm) -> None:
    render, _ = renderer({"plantuml": [SVG, SVG]})  # no mermaid at all
    results = {r.diagram_type: r for r in await render.render_all(cpm)}

    assert isinstance(results["entity_relationship"], FailedDiagram)
    assert "no engine registered" in results["entity_relationship"].error
    assert all(results[t].ok for t in ("class", "use_case"))


async def test_a_mapper_that_raises_fails_only_that_diagram(cpm) -> None:
    def exploding(_cpm):
        raise ValueError("mapper bug")

    broken = DiagramMapper(
        diagram_type="broken",
        title="Broken Diagram",
        engine=Engine.PLANTUML,
        to_source=exploding,
    )
    from diagrams.registry import registry

    mappers = {**registry(), "broken": broken}
    render = DiagramRenderer(
        engines={
            "plantuml": FakeEngine("plantuml", [SVG, SVG]),
            "mermaid": FakeEngine("mermaid", [SVG]),
        },
        mappers=mappers,
    )

    results = {r.diagram_type: r for r in await render.render_all(cpm)}
    assert isinstance(results["broken"], FailedDiagram)
    assert "mapper bug" in results["broken"].error
    assert results["class"].ok


async def test_render_all_never_raises_even_when_everything_fails(cpm) -> None:
    from diagrams.registry import registered_types

    render, _ = renderer(
        {"plantuml": [EngineError("boom")] * 20, "mermaid": [EngineError("boom")] * 20}
    )
    results = await render.render_all(cpm)

    assert len(results) == len(registered_types())
    assert all(isinstance(r, FailedDiagram) for r in results)


async def test_an_unexpected_exception_is_contained_too(cpm) -> None:
    # An engine raising something outside the EngineError hierarchy is a bug,
    # but it still must not abort the sibling diagrams.
    render, _ = renderer({"plantuml": [RuntimeError("unexpected")] * 2, "mermaid": [SVG]})
    # Two named types, not the whole registry: render_all runs concurrently, so
    # a scripted engine with two failures queued would hand them to whichever
    # coroutine happened to start first. Naming the pair makes the test say
    # what it means and stops it breaking when a mapper is added.
    results = {
        r.diagram_type: r for r in await render.render_all(cpm, ["class", "entity_relationship"])
    }

    assert isinstance(results["class"], FailedDiagram)
    assert results["entity_relationship"].ok


# --------------------------------------------------------------------------
# Missing model data is a skip, not a failure
# --------------------------------------------------------------------------


async def test_a_mapper_with_nothing_to_draw_yields_a_skip(cpm) -> None:
    from diagrams.mapper import InsufficientModelData
    from diagrams.types import SkippedDiagram

    def nothing_to_draw(_cpm):
        raise InsufficientModelData("No interaction flows were described.")

    empty = DiagramMapper(
        diagram_type="empty",
        title="Empty Diagram",
        engine=Engine.PLANTUML,
        to_source=nothing_to_draw,
    )
    render = DiagramRenderer(
        engines={"plantuml": FakeEngine("plantuml", [SVG])}, mappers={"empty": empty}
    )
    result = await render.render(cpm, "empty")

    assert isinstance(result, SkippedDiagram)
    assert "No interaction flows" in result.reason


async def test_a_skip_is_not_reported_as_a_failure(cpm) -> None:
    # "We could not draw this" and "you never described this" need different
    # words in the document and different actions from the user.
    from diagrams.mapper import InsufficientModelData
    from diagrams.types import SkippedDiagram
    from generation.run import GenerationRunResult

    def nothing_to_draw(_cpm):
        raise InsufficientModelData("nothing to draw")

    skipped = SkippedDiagram(diagram_type="empty", title="Empty", reason="nothing to draw")
    failed = FailedDiagram("x", "X", "plantuml", "src", "boom", 2)
    result = GenerationRunResult(cpm=cpm, diagrams=[skipped, failed], consistency=None)  # type: ignore[arg-type]

    assert result.skipped == [skipped]
    assert result.failed == [failed], "a skip must not be counted as a failure"
    assert nothing_to_draw is not None


async def test_the_engine_is_never_called_for_a_skipped_diagram(cpm) -> None:
    from diagrams.mapper import InsufficientModelData

    def nothing_to_draw(_cpm):
        raise InsufficientModelData("nothing to draw")

    empty = DiagramMapper("empty", "Empty", Engine.PLANTUML, nothing_to_draw)
    engine = FakeEngine("plantuml", [SVG])
    render = DiagramRenderer(engines={"plantuml": engine}, mappers={"empty": empty})
    await render.render(cpm, "empty")

    assert engine.calls == []


# --------------------------------------------------------------------------
# Selection and format
# --------------------------------------------------------------------------


async def test_a_subset_can_be_requested(cpm) -> None:
    render, _ = renderer({"plantuml": [SVG]})
    results = await render.render_all(cpm, ["class"])
    assert [r.diagram_type for r in results] == ["class"]


async def test_the_requested_format_reaches_the_engine(cpm) -> None:
    render, engines = renderer({"plantuml": [b"\x89PNG\r\n\x1a\nrest"]})
    result = await render.render(cpm, "class", RenderFormat.PNG)

    assert engines["plantuml"].calls[0][1] is RenderFormat.PNG
    assert isinstance(result, RenderedDiagram)
    assert result.fmt is RenderFormat.PNG
