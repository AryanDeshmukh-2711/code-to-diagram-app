"""CPM -> mapper -> source -> engine -> bytes, with failures contained.

`render_all` cannot raise on a diagram-level problem. Every failure mode —
a mapper crash, an unregistered engine, an unreachable server, invalid source —
becomes a `FailedDiagram` in the returned list. That is FR-11 and NFR-R2: one
diagram failing must not abort the remaining artefacts in a run, and a student
waiting three minutes for eight diagrams should not get zero because the
Mermaid renderer was down.
"""

import asyncio
import logging
from collections.abc import Awaitable, Callable, Mapping, Sequence

from cpm.schema import CPM
from diagrams.engines.base import DiagramEngine, EngineError
from diagrams.mapper import DiagramMapper, InsufficientModelData
from diagrams.registry import get_mapper, registered_types
from diagrams.types import (
    DiagramResult,
    FailedDiagram,
    RenderedDiagram,
    RenderFormat,
    SkippedDiagram,
)

logger = logging.getLogger(__name__)

MAX_ATTEMPTS = 2
"""One render, one retry (FR-11). Rendering is deterministic, so a third
attempt on the same source would only cost time — the retry exists for
transient engine trouble, not to wear down a syntax error."""


class DiagramRenderer:
    def __init__(
        self,
        engines: Mapping[str, DiagramEngine],
        mappers: Mapping[str, DiagramMapper] | None = None,
    ) -> None:
        self._engines = dict(engines)
        self._mappers = dict(mappers) if mappers is not None else None

    async def render(
        self, cpm: CPM, diagram_type: str, fmt: RenderFormat = RenderFormat.SVG
    ) -> DiagramResult:
        mapper = self._mapper(diagram_type)

        try:
            source = mapper.to_source(cpm)
        except InsufficientModelData as exc:
            # Not a failure. The model simply does not describe this, and
            # inventing content to fill the figure is the one thing that must
            # not happen here.
            logger.info("skipping %s: %s", diagram_type, exc.reason)
            return SkippedDiagram(
                diagram_type=mapper.diagram_type, title=mapper.title, reason=exc.reason
            )
        except Exception as exc:
            # A mapper bug is still only one diagram's problem.
            logger.exception("mapper for %s raised", diagram_type)
            return FailedDiagram(
                diagram_type=mapper.diagram_type,
                title=mapper.title,
                engine=str(mapper.engine),
                source="",
                error=f"mapper failed: {type(exc).__name__}: {exc}",
                attempts=0,
            )

        engine = self._engines.get(str(mapper.engine))
        if engine is None:
            return FailedDiagram(
                diagram_type=mapper.diagram_type,
                title=mapper.title,
                engine=str(mapper.engine),
                source=source,
                error=(
                    f"no engine registered for {mapper.engine!s}; "
                    f"registered: {', '.join(sorted(self._engines)) or 'none'}"
                ),
                attempts=0,
            )

        last_error = ""
        for attempt in range(1, MAX_ATTEMPTS + 1):
            try:
                content = await engine.render(source, fmt)
            except EngineError as exc:
                last_error = str(exc)
                logger.warning(
                    "render of %s failed on attempt %d/%d: %s",
                    mapper.diagram_type,
                    attempt,
                    MAX_ATTEMPTS,
                    exc,
                )
                continue
            except Exception as exc:
                last_error = f"{type(exc).__name__}: {exc}"
                logger.exception("unexpected error rendering %s", mapper.diagram_type)
                continue

            return RenderedDiagram(
                diagram_type=mapper.diagram_type,
                title=mapper.title,
                engine=engine.name,
                source=source,
                fmt=fmt,
                content=content,
            )

        return FailedDiagram(
            diagram_type=mapper.diagram_type,
            title=mapper.title,
            engine=engine.name,
            source=source,
            error=last_error,
            attempts=MAX_ATTEMPTS,
        )

    async def render_all(
        self,
        cpm: CPM,
        diagram_types: Sequence[str] | None = None,
        fmt: RenderFormat = RenderFormat.SVG,
        on_result: Callable[[DiagramResult], Awaitable[None]] | None = None,
    ) -> list[DiagramResult]:
        """Render several diagrams concurrently. Never raises for one failing.

        `on_result` fires as each diagram finishes rather than at the end, so a
        caller can persist progress while the rest are still running. It is a
        reporting hook only: raising from it must not take the run down.
        """
        wanted = list(diagram_types) if diagram_types is not None else self._known_types()

        async def render_one(diagram_type: str) -> DiagramResult:
            result = await self.render(cpm, diagram_type, fmt)
            if on_result is not None:
                try:
                    await on_result(result)
                except Exception:
                    logger.exception("progress callback failed for %s", diagram_type)
            return result

        results = await asyncio.gather(*(render_one(diagram_type) for diagram_type in wanted))
        return list(results)

    # -- internals ---------------------------------------------------------

    def _mapper(self, diagram_type: str) -> DiagramMapper:
        if self._mappers is None:
            return get_mapper(diagram_type)
        try:
            return self._mappers[diagram_type]
        except KeyError:
            raise KeyError(f"unknown diagram type {diagram_type!r}") from None

    def _known_types(self) -> list[str]:
        return sorted(self._mappers) if self._mappers is not None else registered_types()


def build_default_renderer() -> "DiagramRenderer":
    """A renderer wired from the environment, for the worker."""
    import os

    from diagrams.engines.mermaid import MermaidEngine
    from diagrams.engines.plantuml import PlantUMLEngine

    return DiagramRenderer(
        engines={
            "plantuml": PlantUMLEngine(os.getenv("PLANTUML_SERVER_URL", "http://plantuml:8080")),
            "mermaid": MermaidEngine(os.getenv("MERMAID_RENDERER_URL", "http://kroki:8000")),
        }
    )
