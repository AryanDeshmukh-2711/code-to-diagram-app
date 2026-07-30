"""Mapper discovery.

Every module under `diagrams.mappers` is imported and its `MAPPER` collected.
That is what makes "adding a diagram type is one new file" literally true: no
enum to extend, no registry dict to edit, no import to add.

A module without a `MAPPER` is an error rather than a silent skip — a mapper
that forgot to export one would otherwise vanish from the run with no
indication that a diagram is missing.
"""

import importlib
import pkgutil
from functools import lru_cache

from diagrams import mappers as _mappers_package
from diagrams.mapper import DiagramMapper


class MapperRegistrationError(RuntimeError):
    pass


class UnknownDiagramType(KeyError):
    def __init__(self, diagram_type: str, known: list[str]) -> None:
        super().__init__(
            f"unknown diagram type {diagram_type!r}; registered: {', '.join(sorted(known))}"
        )
        self.diagram_type = diagram_type


@lru_cache(maxsize=1)
def registry() -> dict[str, DiagramMapper]:
    discovered: dict[str, DiagramMapper] = {}

    for module_info in sorted(
        pkgutil.iter_modules(_mappers_package.__path__), key=lambda m: m.name
    ):
        module = importlib.import_module(f"{_mappers_package.__name__}.{module_info.name}")
        mapper = getattr(module, "MAPPER", None)

        if mapper is None:
            raise MapperRegistrationError(
                f"{module.__name__} defines no module-level MAPPER; "
                "every module under diagrams/mappers/ must export one."
            )
        if not isinstance(mapper, DiagramMapper):
            raise MapperRegistrationError(
                f"{module.__name__}.MAPPER is {type(mapper).__name__}, expected DiagramMapper."
            )
        if mapper.diagram_type in discovered:
            raise MapperRegistrationError(
                f"two mappers claim diagram type {mapper.diagram_type!r}: "
                f"{module.__name__} and an earlier module."
            )
        discovered[mapper.diagram_type] = mapper

    return discovered


def get_mapper(diagram_type: str) -> DiagramMapper:
    found = registry()
    try:
        return found[diagram_type]
    except KeyError:
        raise UnknownDiagramType(diagram_type, list(found)) from None


def registered_types() -> list[str]:
    return sorted(registry())
