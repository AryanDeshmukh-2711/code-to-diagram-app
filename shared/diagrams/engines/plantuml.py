"""PlantUML server adapter.

The server accepts the diagram source as a raw POST body and answers **HTTP 400
with a rendered "Syntax Error" image** for broken input — verified against the
running container rather than assumed. So the status code is the primary
validity signal, and the payload shape is checked as a second guard in case a
different server build answers 200 with the same error image.
"""

import httpx

from diagrams.engines.base import EngineError, EngineUnavailable
from diagrams.types import RenderFormat

DEFAULT_BASE_URL = "http://plantuml:8080"

_SVG_PREFIXES = (b"<?xml", b"<svg")
_PNG_MAGIC = b"\x89PNG\r\n\x1a\n"


class PlantUMLEngine:
    name = "plantuml"

    def __init__(
        self,
        base_url: str = DEFAULT_BASE_URL,
        timeout_seconds: float = 30.0,
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
                    f"/{fmt.value}",
                    content=source.encode("utf-8"),
                    headers={"Content-Type": "text/plain; charset=utf-8"},
                )
        except httpx.HTTPError as exc:
            raise EngineUnavailable(
                f"plantuml at {self._base_url} is unreachable: {type(exc).__name__}: {exc}"
            ) from exc

        if response.status_code != httpx.codes.OK:
            raise EngineError(
                f"plantuml rejected the source ({response.status_code}): "
                f"{_error_summary(response.content)}"
            )

        _assert_payload_looks_right(response.content, fmt)
        return response.content


def _assert_payload_looks_right(content: bytes, fmt: RenderFormat) -> None:
    if not content:
        raise EngineError("plantuml returned an empty response")

    if fmt is RenderFormat.SVG:
        if not content.lstrip().startswith(_SVG_PREFIXES):
            raise EngineError("plantuml returned something that is not an SVG document")
    elif not content.startswith(_PNG_MAGIC):
        raise EngineError("plantuml returned something that is not a PNG image")


def _error_summary(content: bytes) -> str:
    text = content.decode("utf-8", errors="replace")
    # The error image embeds the message as SVG text; surface a short slice of
    # it so the failed artefact is diagnosable without opening the picture.
    marker = text.find("Syntax Error")
    if marker != -1:
        return text[marker : marker + 200].replace("\n", " ")
    return text[:200].replace("\n", " ")
