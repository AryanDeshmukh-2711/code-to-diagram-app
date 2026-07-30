"""Mapper discovery, and the "one new file" property.

The design requirement is that adding a ninth diagram type touches exactly one
file. These tests pin the mechanics that make that true: discovery is
automatic, the engine choice lives on the mapper rather than in a switch, and
there is no central enum of types to extend.
"""

from pathlib import Path

import pytest

from diagrams import mappers as mappers_package
from diagrams.mapper import DiagramMapper
from diagrams.registry import (
    UnknownDiagramType,
    get_mapper,
    registered_types,
    registry,
)
from diagrams.types import Engine

MAPPERS_DIR = Path(mappers_package.__file__).resolve().parent

EXPECTED_NOW = {"class", "entity_relationship", "use_case"}


def test_the_three_implemented_types_are_registered() -> None:
    assert EXPECTED_NOW <= set(registered_types())


def test_every_module_in_the_mappers_package_is_discovered() -> None:
    # This is the "one new file" guarantee, stated as a test: drop a module in
    # and it is live. Nothing to add to a registry, an enum, or an __init__.
    modules = {p.stem for p in MAPPERS_DIR.glob("*.py") if p.name != "__init__.py"}
    registered_modules = {
        Path(mapper.to_source.__module__.replace(".", "/")).name for mapper in registry().values()
    }
    assert modules == registered_modules


def test_each_mapper_declares_its_own_engine() -> None:
    # If the engine were chosen by a switch keyed on diagram type, adding a
    # type would mean editing that switch — a second file.
    for diagram_type, mapper in registry().items():
        assert isinstance(mapper.engine, Engine), diagram_type


def test_the_engine_assignments_follow_the_srs_matrix() -> None:
    # SRS §8 is a binding decision, not a default. Mermaid has no use case
    # diagram at all, so that one cannot drift to Mermaid later by accident.
    assert get_mapper("class").engine is Engine.PLANTUML
    assert get_mapper("entity_relationship").engine is Engine.MERMAID
    assert get_mapper("use_case").engine is Engine.PLANTUML


def test_every_mapper_has_a_distinct_slug_and_a_caption() -> None:
    mappers = list(registry().values())
    assert len({m.diagram_type for m in mappers}) == len(mappers)
    for mapper in mappers:
        assert mapper.title.strip(), mapper.diagram_type
        assert mapper.diagram_type.islower()


def test_an_unknown_type_names_the_registered_ones() -> None:
    with pytest.raises(UnknownDiagramType) as excinfo:
        get_mapper("gantt")
    for known in EXPECTED_NOW:
        assert known in str(excinfo.value)


def test_mappers_are_plain_dataclasses_not_subclasses() -> None:
    # Composition over inheritance here is deliberate: a new type supplies a
    # function, it does not have to satisfy an abstract base class.
    for mapper in registry().values():
        assert type(mapper) is DiagramMapper
