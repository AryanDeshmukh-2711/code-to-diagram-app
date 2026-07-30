"""Mermaid adapter, over Kroki's HTTP API.

Mermaid renders in a browser, so any server-side renderer carries a headless
Chromium — roughly a gigabyte of image. The `kroki` and `kroki-mermaid`
services in docker-compose provide it and are **not started by default**;
until they are, ER rendering returns a failed artefact and every other diagram
in the run still completes. That is FR-11 and NFR-R2 doing real work rather
than being a slogan: the infrastructure cost is opt-in because one failing
diagram cannot take the run with it.
"""

import httpx

from diagrams.engines.base import EngineError, EngineUnavailable
from diagrams.types import RenderFormat

DEFAULT_BASE_URL = "http://kroki:8000"

_SVG_PREFIXES = (b"<?xml", b"<svg")
_PNG_MAGIC = b"\x89PNG\r\n\x1a\n"


class MermaidEngine:
    name = "mermaid"

    def __init__(
        self,
        base_url: str = DEFAULT_BASE_URL,
        timeout_seconds: float = 60.0,
        transport: httpx.AsyncBaseTransport | None = None,
    ) -> None:
        self._base_url = base_url.rstrip("/")
        self._timeout = timeout_seconds
        self._transport = transport

    async def render(self, source: str, fmt: RenderFormat) -> bytes:
        try:
            async with httpx.AsyncClient(
                base_url=self._base_url, timeout=self._timeout, transport=self._transport
            ) as client:
                response = await client.post(
                    f"/mermaid/{fmt.value}",
                    content=source.encode("utf-8"),
                    headers={"Content-Type": "text/plain; charset=utf-8"},
                )
        except httpx.HTTPError as exc:
            raise EngineUnavailable(
                f"mermaid renderer at {self._base_url} is unreachable: "
                f"{type(exc).__name__}: {exc}. "
                "Start it with `docker compose up -d kroki kroki-mermaid`."
            ) from exc

        if response.status_code != httpx.codes.OK:
            summary = response.text[:200].replace("\n", " ")
            raise EngineError(
                f"mermaid renderer rejected the source ({response.status_code}): {summary}"
            )

        content = response.content
        if not content:
            raise EngineError("mermaid renderer returned an empty response")

        if fmt is RenderFormat.SVG:
            if not content.lstrip().startswith(_SVG_PREFIXES):
                raise EngineError("mermaid renderer returned something that is not an SVG")
        elif not content.startswith(_PNG_MAGIC):
            raise EngineError("mermaid renderer returned something that is not a PNG")

        return content
