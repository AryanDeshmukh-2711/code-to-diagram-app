"""Cleaning up model output — by removing and merging only, never by adding.

Four jobs, in order, because each depends on the last:

1. **Merge near-identical names.** Book / Books / book are one concept spelled
   three ways, and left alone they become three boxes on a class diagram.
2. **Canonicalise interface names against their component.** `provides` and
   `requires` are free-text `Name` fields, not id references, so the model is
   free to spell a component's own name two ways across the components that
   mention it ("Catalog Service" as its own name, "catalog-service" wherever
   another component requires it). Same reference, different spelling — left
   alone this is exactly the byte-for-byte mismatch FR-10 exists to catch, and
   it would fail the whole run over a spelling difference rather than a real
   inconsistency.
3. **Drop orphan references.** A relationship whose endpoint was never declared
   gets dropped. Inventing the missing endpoint would be fabrication, which is
   exactly what must not happen here.
4. **Order every unordered collection.** So two extractions of the same input
   diff cleanly instead of showing churn the model invented.

The invariant that matters: **nothing here can add an element.** Every step
either merges two existing items or removes one. That is what makes the
completeness floor meaningful — if normalisation could top up a thin model,
the floor would just be measuring its own output.
"""

import re
from dataclasses import dataclass, field

from cpm.schema import Component, CPMCollections, Entity

# Words whose trailing "s" is part of the word, not a plural. Without these,
# "status" stems to "statu" and "address" to "addres", and two unrelated
# entities can collide.
_NON_PLURAL_ENDINGS = ("ss", "us", "is", "as")


def _singular(word: str) -> str:
    if word.endswith(_NON_PLURAL_ENDINGS):
        return word
    if word.endswith("ies") and len(word) > 4:
        return f"{word[:-3]}y"
    if word.endswith(("ches", "shes", "xes", "zes", "ses")):
        return word[:-2]
    if word.endswith("s") and len(word) > 3:
        return word[:-1]
    return word


def canonical_name_key(name: str) -> str:
    """A grouping key — deliberately never used as a display name.

    Stemming is lossy, so it decides only *which names belong together*. The
    name that survives a merge is always one the model actually produced, so a
    bad stem can at worst miss a merge; it can never rename a concept into
    something nobody wrote.
    """
    words = re.sub(r"[^0-9a-z]+", " ", name.casefold()).split()
    if not words:
        return name.casefold().strip()
    words[-1] = _singular(words[-1])
    return " ".join(words)


def normalise_display_name(name: str) -> str:
    """Collapse whitespace, and title-case names that arrived all-lowercase.

    Only all-lowercase names are re-cased. Mixed case and all-caps are left
    alone because they are usually deliberate — title-casing would turn ISBN
    into Isbn and eBook into Ebook.
    """
    collapsed = " ".join(name.split())
    if collapsed and collapsed == collapsed.lower():
        return collapsed.title()
    return collapsed


def _representative(names: list[str]) -> str:
    """Pick which spelling survives a merge.

    Prefers a form that is already singular, then one that is capitalised, then
    the shortest, then alphabetical — so Book beats Books beats book, and the
    choice does not depend on the order the model happened to emit them in.
    """

    def rank(name: str) -> tuple[int, int, int, str]:
        collapsed = " ".join(name.split())
        already_singular = collapsed.casefold() == canonical_name_key(collapsed)
        capitalised = collapsed[:1].isupper()
        return (0 if already_singular else 1, 0 if capitalised else 1, len(collapsed), collapsed)

    return min(names, key=rank)


@dataclass
class NormalisationOutcome:
    collections: CPMCollections
    notes: list[str] = field(default_factory=list)


def normalise(raw: CPMCollections) -> NormalisationOutcome:
    notes: list[str] = []

    entities, entity_id_map = _merge_entities(raw.entities, notes)
    actors, actor_id_map = _merge_actors(raw.actors, notes)

    entity_ids = {entity.id for entity in entities}
    actor_ids = {actor.id for actor in actors}

    relationships = _keep_valid_relationships(raw.relationships, entity_id_map, entity_ids, notes)
    use_cases = _keep_valid_use_cases(raw.use_cases, actor_id_map, actor_ids, notes)
    states = _keep_valid_states(raw.states, entity_id_map, entity_ids, notes)
    components = _canonicalise_components(raw.components, notes)
    component_ids = {component.id for component in components}
    nodes = _keep_valid_nodes(raw.nodes, component_ids, notes)
    flows = _keep_valid_flows(
        raw.flows, entity_id_map | actor_id_map, entity_ids | actor_ids, notes
    )

    ordered = CPMCollections(
        actors=sorted(actors, key=lambda a: a.id),
        entities=sorted((_order_entity(e) for e in entities), key=lambda e: e.id),
        relationships=sorted(relationships, key=lambda r: (r.from_, r.to, r.type.value, r.id)),
        use_cases=sorted(use_cases, key=lambda u: u.id),
        flows=sorted(flows, key=lambda f: f.id),
        states=sorted(states, key=lambda s: (s.entity_ref, s.id)),
        components=sorted(components, key=lambda c: c.id),
        nodes=sorted(nodes, key=lambda n: n.id),
        requirements=sorted(raw.requirements, key=lambda r: r.id),
    )
    return NormalisationOutcome(collections=ordered, notes=notes)


# -- merging ---------------------------------------------------------------


def _group_by_name(items: list) -> dict[str, list]:
    grouped: dict[str, list] = {}
    for item in items:
        grouped.setdefault(canonical_name_key(item.name), []).append(item)
    return grouped


def _merge_entities(
    entities: list[Entity], notes: list[str]
) -> tuple[list[Entity], dict[str, str]]:
    merged: list[Entity] = []
    id_map: dict[str, str] = {}

    for group in _group_by_name(entities).values():
        winner_name = _representative([item.name for item in group])
        winner = next(item for item in group if item.name == winner_name)

        # Union the attributes and methods rather than keeping only the
        # winner's — merging must not quietly delete fields the duplicates
        # carried, which would be data loss dressed up as tidying.
        attributes = {}
        methods = {}
        for item in group:
            id_map[item.id] = winner.id
            for attribute in item.attributes:
                attributes.setdefault(attribute.name, attribute)
            for method in item.methods:
                methods.setdefault(method.name, method)

        descriptions = [item.description for item in group if item.description]

        merged.append(
            winner.model_copy(
                update={
                    "name": normalise_display_name(winner.name),
                    "description": max(descriptions, key=len) if descriptions else "",
                    "attributes": list(attributes.values()),
                    "methods": list(methods.values()),
                }
            )
        )

        if len(group) > 1:
            others = sorted(item.name for item in group if item.id != winner.id)
            notes.append(
                f"Merged {len(group)} entity names into "
                f"{normalise_display_name(winner.name)!r}: {', '.join(others)}."
            )

    return merged, id_map


def _merge_actors(actors: list, notes: list[str]) -> tuple[list, dict[str, str]]:
    merged = []
    id_map: dict[str, str] = {}

    for group in _group_by_name(actors).values():
        winner_name = _representative([item.name for item in group])
        winner = next(item for item in group if item.name == winner_name)
        for item in group:
            id_map[item.id] = winner.id

        descriptions = [item.description for item in group if item.description]
        merged.append(
            winner.model_copy(
                update={
                    "name": normalise_display_name(winner.name),
                    "description": max(descriptions, key=len) if descriptions else "",
                }
            )
        )

        if len(group) > 1:
            others = sorted(item.name for item in group if item.id != winner.id)
            notes.append(
                f"Merged {len(group)} actor names into "
                f"{normalise_display_name(winner.name)!r}: {', '.join(others)}."
            )

    return merged, id_map


def _canonicalise_components(components: list[Component], notes: list[str]) -> list[Component]:
    """Rewrite each `provides`/`requires` entry to match a component's name,
    when the two are the same reference spelled differently.

    `canonical_name_key` is the same grouping key entity names merge on
    above — it is what already knows "Catalog Service" and "catalog-service"
    are one concept, so reusing it here needs no new matching logic. A name
    that matches no component (a genuine interface, not a component
    reference) is left as-is beyond the usual whitespace/case cleanup — only
    an actual match gets rewritten, never invented.
    """
    canonical_by_key = {
        canonical_name_key(component.name): component.name for component in components
    }

    def canonicalise(name: str) -> str:
        return canonical_by_key.get(canonical_name_key(name), normalise_display_name(name))

    updated = []
    for component in components:
        provides = [canonicalise(name) for name in component.provides]
        requires = [canonicalise(name) for name in component.requires]
        if provides != list(component.provides) or requires != list(component.requires):
            notes.append(
                f"Canonicalised interface names on component {component.id!r} to match "
                "the component name they referred to."
            )
        updated.append(
            component.model_copy(
                update={
                    "name": normalise_display_name(component.name),
                    "provides": provides,
                    "requires": requires,
                }
            )
        )
    return updated


# -- dropping orphans ------------------------------------------------------


def _keep_valid_relationships(relationships, id_map, entity_ids, notes):
    kept = []
    for relationship in relationships:
        source = id_map.get(relationship.from_, relationship.from_)
        target = id_map.get(relationship.to, relationship.to)
        missing = [ref for ref in (source, target) if ref not in entity_ids]
        if missing:
            # Dropped, never repaired: inventing the missing entity is the
            # fabrication this whole module exists to avoid.
            notes.append(
                f"Dropped relationship {relationship.id!r}: "
                f"{', '.join(repr(ref) for ref in missing)} is not a declared entity."
            )
            continue
        kept.append(relationship.model_copy(update={"from_": source, "to": target}))
    return kept


def _keep_valid_use_cases(use_cases, id_map, actor_ids, notes):
    kept = []
    for use_case in use_cases:
        resolved = [id_map.get(actor, actor) for actor in use_case.actors]
        valid = [actor for actor in resolved if actor in actor_ids]
        dropped = sorted(set(resolved) - set(valid))
        if dropped:
            notes.append(
                f"Dropped undeclared actors from use case {use_case.id!r}: "
                f"{', '.join(repr(a) for a in dropped)}."
            )
        kept.append(use_case.model_copy(update={"actors": sorted(dict.fromkeys(valid))}))
    return kept


def _keep_valid_states(states, id_map, entity_ids, notes):
    resolved = []
    for state in states:
        entity_ref = id_map.get(state.entity_ref, state.entity_ref)
        if entity_ref not in entity_ids:
            notes.append(
                f"Dropped state {state.id!r}: entity {state.entity_ref!r} was never declared."
            )
            continue
        resolved.append(state.model_copy(update={"entity_ref": entity_ref}))

    entity_by_state = {state.id: state.entity_ref for state in resolved}

    kept = []
    for state in resolved:
        transitions = []
        for transition in state.transitions:
            target_entity = entity_by_state.get(transition.to)
            if target_entity is None:
                notes.append(
                    f"Dropped transition from {state.id!r}: "
                    f"target state {transition.to!r} does not exist."
                )
                continue
            if target_entity != state.entity_ref:
                notes.append(
                    f"Dropped transition from {state.id!r} to {transition.to!r}: "
                    "a state machine is drawn per entity and these belong to different ones."
                )
                continue
            transitions.append(transition)
        kept.append(
            state.model_copy(
                update={
                    "name": normalise_display_name(state.name),
                    "transitions": sorted(transitions, key=lambda t: (t.to, t.trigger or "")),
                }
            )
        )
    return kept


def _keep_valid_nodes(nodes, component_ids, notes):
    kept = []
    for node in nodes:
        valid = [ref for ref in node.deployed_components if ref in component_ids]
        dropped = sorted(set(node.deployed_components) - set(valid))
        if dropped:
            notes.append(
                f"Dropped undeclared components from node {node.id!r}: "
                f"{', '.join(repr(c) for c in dropped)}."
            )
        kept.append(node.model_copy(update={"deployed_components": sorted(valid)}))
    return kept


def _keep_valid_flows(flows, id_map, participant_ids, notes):
    kept = []
    for flow in flows:
        resolved = [id_map.get(p, p) for p in flow.participants]
        participants = sorted(dict.fromkeys(p for p in resolved if p in participant_ids))
        dropped = sorted(set(resolved) - set(participants))
        if dropped:
            notes.append(
                f"Dropped undeclared participants from flow {flow.id!r}: "
                f"{', '.join(repr(p) for p in dropped)}."
            )

        steps = []
        for step in flow.steps:
            source = id_map.get(step.from_, step.from_)
            target = id_map.get(step.to, step.to)
            if source not in participants or target not in participants:
                notes.append(
                    f"Dropped step {step.order} of flow {flow.id!r}: "
                    "it addressed a participant that is not in the flow."
                )
                continue
            steps.append(step.model_copy(update={"from_": source, "to": target}))

        kept.append(
            flow.model_copy(
                update={
                    "participants": participants,
                    "steps": sorted(steps, key=lambda s: (s.order, s.from_, s.to)),
                }
            )
        )
    return kept


# -- ordering --------------------------------------------------------------


def _order_entity(entity: Entity) -> Entity:
    return entity.model_copy(
        update={
            # Keys first, then alphabetical: sorted for diffability, but a
            # class diagram that leads with the primary key reads correctly.
            "attributes": sorted(entity.attributes, key=lambda a: (not a.is_key, a.name)),
            "methods": sorted(entity.methods, key=lambda m: m.name),
        }
    )
