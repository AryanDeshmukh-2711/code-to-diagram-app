"""Engine adapters, driven through httpx.MockTransport.

The behaviour that matters most is rejecting bad output. A PlantUML server
handed broken syntax answers with a *perfectly valid SVG* whose content is the
words "Syntax Error" — verified against the running container, which returns
HTTP 400 alongside it. An adapter that only checked "did I get bytes" would
hand that picture straight into a submitted document.
"""

import httpx
import pytest

from diagrams.engines.base import EngineError, EngineUnavailable
from diagrams.engines.mermaid import MermaidEngine
from diagrams.engines.plantuml import PlantUMLEngine
from diagrams.types import RenderFormat

SVG = b"<svg xmlns='http://www.w3.org/2000/svg'>ok</svg>"
PNG = b"\x89PNG\r\n\x1a\nrest-of-image"
ERROR_SVG = b"<svg xmlns='http://www.w3.org/2000/svg'><text>Syntax Error?</text></svg>"


def responding(status: int, content: bytes, captured: list | None = None) -> httpx.MockTransport:
    def handler(request: httpx.Request) -> httpx.Response:
        if captured is not None:
            captured.append(request)
        return httpx.Response(status, content=content)

    return httpx.MockTransport(handler)


# --------------------------------------------------------------------------
# PlantUML
# --------------------------------------------------------------------------


async def test_plantuml_posts_the_source_to_the_format_endpoint() -> None:
    captured: list[httpx.Request] = []
    engine = PlantUMLEngine("http://plantuml:8080", transport=responding(200, SVG, captured))
    await engine.render("@startuml\n@enduml\n", RenderFormat.SVG)

    assert captured[0].url.path == "/svg"
    assert captured[0].method == "POST"
    assert captured[0].content == b"@startuml\n@enduml\n"


async def test_plantuml_returns_the_rendered_bytes() -> None:
    engine = PlantUMLEngine("http://plantuml:8080", transport=responding(200, SVG))
    assert await engine.render("@startuml\n@enduml\n", RenderFormat.SVG) == SVG


async def test_plantuml_uses_the_png_endpoint_for_png() -> None:
    captured: list[httpx.Request] = []
    engine = PlantUMLEngine("http://plantuml:8080", transport=responding(200, PNG, captured))
    await engine.render("@startuml\n@enduml\n", RenderFormat.PNG)
    assert captured[0].url.path == "/png"


async def test_plantuml_rejects_a_syntax_error_response() -> None:
    engine = PlantUMLEngine("http://plantuml:8080", transport=responding(400, ERROR_SVG))
    with pytest.raises(EngineError) as excinfo:
        await engine.render("@startuml\nbroken {{{\n@enduml\n", RenderFormat.SVG)

    assert "400" in str(excinfo.value)
    assert "Syntax Error" in str(excinfo.value), "the message should say what went wrong"


async def test_plantuml_rejects_a_non_svg_payload_even_on_a_200() -> None:
    # Second line of defence: if a server build answers 200 with an error page,
    # "it returned bytes" must not count as success.
    engine = PlantUMLEngine("http://plantuml:8080", transport=responding(200, b"<html>oops"))
    with pytest.raises(EngineError, match="not an SVG"):
        await engine.render("@startuml\n@enduml\n", RenderFormat.SVG)


async def test_plantuml_rejects_a_non_png_payload() -> None:
    engine = PlantUMLEngine("http://plantuml:8080", transport=responding(200, SVG))
    with pytest.raises(EngineError, match="not a PNG"):
        await engine.render("@startuml\n@enduml\n", RenderFormat.PNG)


async def test_plantuml_rejects_an_empty_response() -> None:
    engine = PlantUMLEngine("http://plantuml:8080", transport=responding(200, b""))
    with pytest.raises(EngineError, match="empty"):
        await engine.render("@startuml\n@enduml\n", RenderFormat.SVG)


async def test_an_unreachable_plantuml_is_reported_as_unavailable() -> None:
    def refuse(_request: httpx.Request) -> httpx.Response:
        raise httpx.ConnectError("connection refused")

    engine = PlantUMLEngine("http://plantuml:8080", transport=httpx.MockTransport(refuse))
    with pytest.raises(EngineUnavailable, match="unreachable"):
        await engine.render("@startuml\n@enduml\n", RenderFormat.SVG)


# --------------------------------------------------------------------------
# Mermaid (Kroki)
# --------------------------------------------------------------------------


async def test_mermaid_posts_to_the_mermaid_route() -> None:
    captured: list[httpx.Request] = []
    engine = MermaidEngine("http://kroki:8000", transport=responding(200, SVG, captured))
    await engine.render("erDiagram\n", RenderFormat.SVG)

    assert captured[0].url.path == "/mermaid/svg"
    assert captured[0].content == b"erDiagram\n"


async def test_mermaid_returns_the_rendered_bytes() -> None:
    engine = MermaidEngine("http://kroki:8000", transport=responding(200, SVG))
    assert await engine.render("erDiagram\n", RenderFormat.SVG) == SVG


async def test_mermaid_rejects_bad_source() -> None:
    engine = MermaidEngine("http://kroki:8000", transport=responding(400, b"Parse error on line 2"))
    with pytest.raises(EngineError, match="Parse error"):
        await engine.render("erDiagram\n  ???\n", RenderFormat.SVG)


async def test_an_unreachable_mermaid_renderer_says_how_to_start_it() -> None:
    # This is the common case in development, so the error is actionable
    # rather than just accurate.
    def refuse(_request: httpx.Request) -> httpx.Response:
        raise httpx.ConnectError("nodename nor servname provided")

    engine = MermaidEngine("http://kroki:8000", transport=httpx.MockTransport(refuse))
    with pytest.raises(EngineUnavailable) as excinfo:
        await engine.render("erDiagram\n", RenderFormat.SVG)
    assert "docker compose up" in str(excinfo.value)
