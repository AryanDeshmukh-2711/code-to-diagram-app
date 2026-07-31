"""FR-10: every name in every artefact is byte-identical to the CPM.

This is a product guarantee, not a lint. The differentiator being sold is that
the class diagram, the ER diagram and the SRS all describe the *same* entity
set with the *same* names; a run where one diagram says "Books" and another
says "Book" has failed at the thing the product exists to do, however good it
looks.

The check is deliberately type-agnostic. It does not know that class diagrams
show entities and use case diagrams show actors — encoding that would mean
editing the validator every time a diagram type is added. Instead: any token
that *resembles* a CPM name must *be* one, byte for byte.

Resemblance reuses the same canonical key as extraction's de-duplication, so
"Books", "book" and "Book  " all resolve to the concept they drifted from and
are reported against it.
"""

from dataclasses import dataclass, field

from consistency.names import extract_names
from cpm.schema import CPM
from extraction.normalise import canonical_name_key


@dataclass(frozen=True)
class NameViolation:
    diagram_type: str
    line: int
    expected: str
    found: str
    context: str

    def render(self) -> str:
        return (
            f"  {self.diagram_type} (line {self.line}): "
            f"expected {self.expected!r}, found {self.found!r}\n"
            f"      {self.context}"
        )


@dataclass(frozen=True)
class ConsistencyReport:
    violations: list[NameViolation] = field(default_factory=list)
    checked_diagrams: int = 0
    recognised_names: int = 0

    @property
    def ok(self) -> bool:
        return not self.violations

    def render(self) -> str:
        if self.ok:
            return (
                f"FR-10 consistency: OK — {self.recognised_names} names checked "
                f"across {self.checked_diagrams} sources."
            )
        lines = [
            f"FR-10 consistency FAILED — {len(self.violations)} "
            f"mismatch{'' if len(self.violations) == 1 else 'es'} "
            f"across {self.checked_diagrams} sources:",
        ]
        lines.extend(violation.render() for violation in self.violations)
        return "\n".join(lines)


class ConsistencyViolation(RuntimeError):
    """A generation run produced artefacts that disagree with the CPM."""

    def __init__(self, report: ConsistencyReport) -> None:
        super().__init__(report.render())
        self.report = report


def cpm_display_names(cpm: CPM) -> set[str]:
    """Every name a diagram could legitimately show."""
    names: set[str] = set()
    names.update(entity.name for entity in cpm.entities)
    names.update(actor.name for actor in cpm.actors)
    names.update(use_case.name for use_case in cpm.use_cases)
    names.update(flow.name for flow in cpm.flows)
    names.update(state.name for state in cpm.states)
    names.update(component.name for component in cpm.components)
    names.update(node.name for node in cpm.nodes)
    names.update(relationship.label for relationship in cpm.relationships if relationship.label)
    names.add(cpm.meta.project_name)
    return names


def validate_stale_names(cpm: CPM, diagrams, previous_names) -> ConsistencyReport:
    """Names a carried-forward figure still shows that the model no longer has.

    `validate_consistency` cannot see this, and the reason is worth stating.
    It flags a token that *resembles* a CPM name but is spelled differently —
    "Books" against "Book". A figure left over from before a rename shows
    "Book" when the model now says "Publication", and those two share no
    canonical key, so the token looks like any other unrecognised word in the
    source: a cardinality, a stereotype, a keyword. Guessing at unknown tokens
    would make the validator a source of false alarms.

    Selective regeneration is the only thing that produces such a set — a full
    run draws every diagram from one model — so it is checked here, using
    something the text alone does not carry: which CPM version each artefact
    was actually drawn from.

    `previous_names` maps a diagram type to the display names of the version it
    was drawn from, so only names that were once legitimately in the model are
    reported. A stray word in a source is still ignored.
    """
    current = cpm_display_names(cpm)
    current_keys = {canonical_name_key(name) for name in current}

    violations: list[NameViolation] = []
    checked = 0

    for diagram in diagrams:
        source = getattr(diagram, "source", "")
        was_known = previous_names.get(diagram.diagram_type)
        if not source or not was_known:
            continue
        checked += 1

        for found in extract_names(source, str(diagram.engine)):
            if found.text in current or canonical_name_key(found.text) in current_keys:
                continue
            if found.text not in was_known:
                continue  # never a model name — not this check's business
            violations.append(
                NameViolation(
                    diagram_type=diagram.diagram_type,
                    line=found.line,
                    expected="a name the current model still has",
                    found=found.text,
                    context=(
                        f"{found.context}  <- drawn from an earlier version of "
                        f"the model; regenerate this diagram too"
                    ),
                )
            )

    return ConsistencyReport(violations=violations, checked_diagrams=checked)


def validate_consistency(cpm: CPM, diagrams) -> ConsistencyReport:
    """Check every diagram's source against the CPM's names.

    `diagrams` is any iterable of results carrying `.diagram_type`, `.engine`
    and `.source` — failed artefacts included, because a source that was
    generated is a source that could be handed to a user for diagnosis.
    """
    exact = cpm_display_names(cpm)
    by_key: dict[str, set[str]] = {}
    for name in exact:
        by_key.setdefault(canonical_name_key(name), set()).add(name)

    violations: list[NameViolation] = []
    checked = 0
    recognised = 0

    for diagram in diagrams:
        source = getattr(diagram, "source", "")
        if not source:
            continue
        checked += 1

        # Spans of candidates that already matched a CPM name exactly. A longer
        # name swallows the shorter candidates inside it: "Borrow Book" is the
        # use case, and "Borrow" is not a second reference that happens to be
        # misspelt. Extractors that emit non-overlapping tokens set no span and
        # are unaffected.
        consumed: list[tuple[int, int]] = []

        for found in extract_names(source, str(diagram.engine)):
            if found.span and any(
                start <= found.span[0] and found.span[1] <= end for start, end in consumed
            ):
                continue

            if found.text in exact:
                recognised += 1
                if found.span:
                    consumed.append(found.span)
                continue

            candidates = by_key.get(canonical_name_key(found.text))
            if not candidates:
                continue  # not a CPM concept at all — a cardinality, a keyword

            # It resolves to a CPM concept but is not spelled the same way.
            violations.append(
                NameViolation(
                    diagram_type=diagram.diagram_type,
                    line=found.line,
                    expected=sorted(candidates)[0],
                    found=found.text,
                    context=found.context,
                )
            )

    if exact and checked and recognised == 0:
        # The extractor found nothing it recognised. Passing on that would mean
        # the guarantee is being met by not looking.
        violations.append(
            NameViolation(
                diagram_type="<run>",
                line=0,
                expected="at least one CPM name to be found in the generated sources",
                found="none",
                context="name extraction recognised nothing — the extractor is broken",
            )
        )

    return ConsistencyReport(
        violations=violations, checked_diagrams=checked, recognised_names=recognised
    )
