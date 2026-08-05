"""Component interface canonicalisation — the fix for FR-10 failing over a
spelling difference rather than a real inconsistency (a component's name
written one way on itself and another way in a sibling's `requires`)."""

from cpm.schema import Component, CPMCollections
from extraction.normalise import normalise


def _components(*components: Component) -> CPMCollections:
    return CPMCollections(components=list(components))


def test_a_slug_shaped_requires_entry_is_rewritten_to_the_components_name() -> None:
    raw = _components(
        Component(
            id="catalog-service",
            name="Catalog Service",
            type="service",
            provides=["Catalog Service"],
        ),
        Component(
            id="web-app", name="Web Application", type="service", requires=["catalog-service"]
        ),
    )

    result = normalise(raw)

    web_app = next(c for c in result.collections.components if c.id == "web-app")
    assert web_app.requires == ["Catalog Service"]


def test_a_provides_entry_matching_no_component_is_left_alone() -> None:
    raw = _components(
        Component(
            id="catalog-service",
            name="Catalog Service",
            type="service",
            provides=["Book Search API"],
        ),
    )

    result = normalise(raw)

    catalog = next(c for c in result.collections.components if c.id == "catalog-service")
    assert catalog.provides == ["Book Search API"]


def test_an_all_lowercase_interface_name_with_no_match_is_title_cased() -> None:
    raw = _components(
        Component(
            id="loan-service", name="Loan Service", type="service", requires=["member database"]
        ),
    )

    result = normalise(raw)

    loan = next(c for c in result.collections.components if c.id == "loan-service")
    assert loan.requires == ["Member Database"]


def test_a_component_name_written_all_lowercase_is_title_cased() -> None:
    raw = _components(Component(id="loan-service", name="loan service", type="service"))

    result = normalise(raw)

    assert result.collections.components[0].name == "Loan Service"


def test_canonicalisation_is_reported() -> None:
    raw = _components(
        Component(id="catalog-service", name="Catalog Service", type="service"),
        Component(
            id="web-app", name="Web Application", type="service", requires=["catalog-service"]
        ),
    )

    result = normalise(raw)

    assert any("canonicalised" in note.lower() for note in result.notes)


def test_an_untouched_component_produces_no_note() -> None:
    raw = _components(
        Component(
            id="catalog-service",
            name="Catalog Service",
            type="service",
            provides=["Catalog Service"],
        ),
    )

    result = normalise(raw)

    assert result.notes == []
