"""Edits on a CPM draft.

Every operation is a **pure function returning a new draft**. Nothing mutates
in place, so "atomically" is structural rather than a promise: if an operation
raises, the caller still holds the original draft, unchanged. There is no
half-applied rename to recover from.

Renaming is the operation that matters. CPM references are by id, and ids are
slugs derived from names — so renaming an entity re-derives its id and rewrites
every reference to it in the same pass: relationships, use case actor lists,
state ownership, flow participants and their steps, and deployed components.
Renaming without that cascade would leave `id: "bookk"` sitting under a
corrected "Book", and the id is what the diagram mappers key on.
"""

from dataclasses import dataclass

from cpm.ids import slugify
from cpm.schema import CPMDraft
from review.errors import InvalidName, NameCollision, UnknownElement


@dataclass(frozen=True)
class EditOutcome:
    """The new draft, plus what the edit touched.

    `references_updated` is surfaced in the UI. A rename that silently fixes
    six references is indistinguishable from one that fixed none, and the
    entire point of this screen is that the user can see what happened.
    """

    draft: CPMDraft
    summary: str
    references_updated: int = 0


def _require(collection, element_id: str, kind: str):
    for item in collection:
        if item.id == element_id:
            return item
    raise UnknownElement(kind, element_id)


def _new_id(name: str, kind: str) -> str:
    cleaned = " ".join(name.split())
    if not cleaned:
        raise InvalidName("A name cannot be empty.")
    try:
        return slugify(cleaned)
    except ValueError:
        raise InvalidName(
            f"{cleaned!r} has no letters or digits, so it cannot be used as a {kind} name."
        ) from None


# --------------------------------------------------------------------------
# Renaming — the cascade
# --------------------------------------------------------------------------


def rename_entity(draft: CPMDraft, entity_id: str, new_name: str) -> EditOutcome:
    entity = _require(draft.entities, entity_id, "entity")
    cleaned = " ".join(new_name.split())
    new_id = _new_id(cleaned, "entity")

    if new_id != entity_id and any(other.id == new_id for other in draft.entities):
        raise NameCollision("entity", cleaned)

    data = draft.model_dump(by_alias=True)
    touched = 0

    for item in data["entities"]:
        if item["id"] == entity_id:
            item["id"] = new_id
            item["name"] = cleaned

    if new_id != entity_id:
        for relationship in data["relationships"]:
            for end in ("from", "to"):
                if relationship[end] == entity_id:
                    relationship[end] = new_id
                    touched += 1

        for state in data["states"]:
            if state["entityRef"] == entity_id:
                state["entityRef"] = new_id
                touched += 1

        for flow in data["flows"]:
            flow["participants"] = [
                new_id if participant == entity_id else participant
                for participant in flow["participants"]
            ]
            touched += flow["participants"].count(new_id) if entity_id != new_id else 0
            for step in flow["steps"]:
                for end in ("from", "to"):
                    if step[end] == entity_id:
                        step[end] = new_id
                        touched += 1

    return EditOutcome(
        draft=CPMDraft.model_validate(data),
        summary=f"Renamed “{entity.name}” to “{cleaned}”",
        references_updated=touched,
    )


def rename_actor(draft: CPMDraft, actor_id: str, new_name: str) -> EditOutcome:
    actor = _require(draft.actors, actor_id, "actor")
    cleaned = " ".join(new_name.split())
    new_id = _new_id(cleaned, "actor")

    if new_id != actor_id and any(other.id == new_id for other in draft.actors):
        raise NameCollision("actor", cleaned)

    data = draft.model_dump(by_alias=True)
    touched = 0

    for item in data["actors"]:
        if item["id"] == actor_id:
            item["id"] = new_id
            item["name"] = cleaned

    if new_id != actor_id:
        for use_case in data["useCases"]:
            renamed = [new_id if actor == actor_id else actor for actor in use_case["actors"]]
            touched += sum(1 for a in use_case["actors"] if a == actor_id)
            use_case["actors"] = renamed

        for flow in data["flows"]:
            touched += sum(1 for p in flow["participants"] if p == actor_id)
            flow["participants"] = [
                new_id if participant == actor_id else participant
                for participant in flow["participants"]
            ]
            for step in flow["steps"]:
                for end in ("from", "to"):
                    if step[end] == actor_id:
                        step[end] = new_id
                        touched += 1

    return EditOutcome(
        draft=CPMDraft.model_validate(data),
        summary=f"Renamed “{actor.name}” to “{cleaned}”",
        references_updated=touched,
    )


def rename_use_case(draft: CPMDraft, use_case_id: str, new_name: str) -> EditOutcome:
    use_case = _require(draft.use_cases, use_case_id, "use case")
    cleaned = " ".join(new_name.split())
    new_id = _new_id(cleaned, "use case")

    if new_id != use_case_id and any(other.id == new_id for other in draft.use_cases):
        raise NameCollision("use case", cleaned)

    data = draft.model_dump(by_alias=True)
    for item in data["useCases"]:
        if item["id"] == use_case_id:
            item["id"] = new_id
            item["name"] = cleaned

    return EditOutcome(
        draft=CPMDraft.model_validate(data), summary=f"Renamed “{use_case.name}” to “{cleaned}”"
    )


# --------------------------------------------------------------------------
# Deleting — also a cascade
# --------------------------------------------------------------------------


def delete_entity(draft: CPMDraft, entity_id: str) -> EditOutcome:
    entity = _require(draft.entities, entity_id, "entity")
    data = draft.model_dump(by_alias=True)
    removed = 0

    data["entities"] = [e for e in data["entities"] if e["id"] != entity_id]

    before = len(data["relationships"])
    data["relationships"] = [
        r for r in data["relationships"] if entity_id not in (r["from"], r["to"])
    ]
    removed += before - len(data["relationships"])

    before = len(data["states"])
    data["states"] = [s for s in data["states"] if s["entityRef"] != entity_id]
    removed += before - len(data["states"])

    surviving_states = {s["id"] for s in data["states"]}
    for state in data["states"]:
        state["transitions"] = [t for t in state["transitions"] if t["to"] in surviving_states]

    for flow in data["flows"]:
        removed += flow["participants"].count(entity_id)
        flow["participants"] = [p for p in flow["participants"] if p != entity_id]
        before = len(flow["steps"])
        flow["steps"] = [s for s in flow["steps"] if entity_id not in (s["from"], s["to"])]
        removed += before - len(flow["steps"])

    return EditOutcome(
        draft=CPMDraft.model_validate(data),
        summary=f"Deleted “{entity.name}”",
        references_updated=removed,
    )


def delete_actor(draft: CPMDraft, actor_id: str) -> EditOutcome:
    actor = _require(draft.actors, actor_id, "actor")
    data = draft.model_dump(by_alias=True)
    removed = 0

    data["actors"] = [a for a in data["actors"] if a["id"] != actor_id]

    for use_case in data["useCases"]:
        removed += use_case["actors"].count(actor_id)
        use_case["actors"] = [a for a in use_case["actors"] if a != actor_id]

    for flow in data["flows"]:
        removed += flow["participants"].count(actor_id)
        flow["participants"] = [p for p in flow["participants"] if p != actor_id]
        before = len(flow["steps"])
        flow["steps"] = [s for s in flow["steps"] if actor_id not in (s["from"], s["to"])]
        removed += before - len(flow["steps"])

    return EditOutcome(
        draft=CPMDraft.model_validate(data),
        summary=f"Deleted “{actor.name}”",
        references_updated=removed,
    )


def delete_relationship(draft: CPMDraft, relationship_id: str) -> EditOutcome:
    _require(draft.relationships, relationship_id, "relationship")
    data = draft.model_dump(by_alias=True)
    data["relationships"] = [r for r in data["relationships"] if r["id"] != relationship_id]
    return EditOutcome(draft=CPMDraft.model_validate(data), summary="Deleted relationship")


def delete_use_case(draft: CPMDraft, use_case_id: str) -> EditOutcome:
    use_case = _require(draft.use_cases, use_case_id, "use case")
    data = draft.model_dump(by_alias=True)
    data["useCases"] = [u for u in data["useCases"] if u["id"] != use_case_id]
    return EditOutcome(draft=CPMDraft.model_validate(data), summary=f"Deleted “{use_case.name}”")


def delete_attribute(draft: CPMDraft, entity_id: str, attribute_name: str) -> EditOutcome:
    _require(draft.entities, entity_id, "entity")
    data = draft.model_dump(by_alias=True)
    for entity in data["entities"]:
        if entity["id"] == entity_id:
            entity["attributes"] = [a for a in entity["attributes"] if a["name"] != attribute_name]
    return EditOutcome(draft=CPMDraft.model_validate(data), summary=f"Removed “{attribute_name}”")


# --------------------------------------------------------------------------
# Adding
# --------------------------------------------------------------------------


def add_entity(draft: CPMDraft, name: str) -> EditOutcome:
    cleaned = " ".join(name.split())
    new_id = _new_id(cleaned, "entity")
    if any(entity.id == new_id for entity in draft.entities):
        raise NameCollision("entity", cleaned)

    data = draft.model_dump(by_alias=True)
    data["entities"].append(
        {"id": new_id, "name": cleaned, "description": "", "attributes": [], "methods": []}
    )
    return EditOutcome(draft=CPMDraft.model_validate(data), summary=f"Added “{cleaned}”")


def add_actor(draft: CPMDraft, name: str) -> EditOutcome:
    cleaned = " ".join(name.split())
    new_id = _new_id(cleaned, "actor")
    if any(actor.id == new_id for actor in draft.actors):
        raise NameCollision("actor", cleaned)

    data = draft.model_dump(by_alias=True)
    data["actors"].append({"id": new_id, "name": cleaned, "description": "", "isPrimary": False})
    return EditOutcome(draft=CPMDraft.model_validate(data), summary=f"Added “{cleaned}”")


def add_attribute(
    draft: CPMDraft, entity_id: str, name: str, type_name: str = "string"
) -> EditOutcome:
    entity = _require(draft.entities, entity_id, "entity")
    cleaned = " ".join(name.split())
    if not cleaned:
        raise InvalidName("An attribute needs a name.")
    if any(attribute.name == cleaned for attribute in entity.attributes):
        raise NameCollision("attribute", cleaned)

    data = draft.model_dump(by_alias=True)
    for item in data["entities"]:
        if item["id"] == entity_id:
            item["attributes"].append(
                {
                    "name": cleaned,
                    "type": type_name or "string",
                    "isKey": False,
                    "isRequired": False,
                }
            )
    return EditOutcome(draft=CPMDraft.model_validate(data), summary=f"Added “{cleaned}”")


def add_relationship(
    draft: CPMDraft,
    from_id: str,
    to_id: str,
    relationship_type: str = "association",
    label: str | None = None,
    cardinality: str | None = None,
) -> EditOutcome:
    _require(draft.entities, from_id, "entity")
    _require(draft.entities, to_id, "entity")

    base = f"r-{from_id}-{to_id}"
    identifier = base
    suffix = 2
    existing = {relationship.id for relationship in draft.relationships}
    while identifier in existing:
        identifier = f"{base}-{suffix}"
        suffix += 1

    data = draft.model_dump(by_alias=True)
    data["relationships"].append(
        {
            "id": identifier,
            "from": from_id,
            "to": to_id,
            "type": relationship_type,
            "label": label or None,
            "cardinality": cardinality or None,
        }
    )
    return EditOutcome(draft=CPMDraft.model_validate(data), summary="Added relationship")


# --------------------------------------------------------------------------
# Re-linking
# --------------------------------------------------------------------------


def relink_relationship(
    draft: CPMDraft,
    relationship_id: str,
    from_id: str | None = None,
    to_id: str | None = None,
    relationship_type: str | None = None,
    label: str | None = None,
    cardinality: str | None = None,
) -> EditOutcome:
    _require(draft.relationships, relationship_id, "relationship")
    if from_id is not None:
        _require(draft.entities, from_id, "entity")
    if to_id is not None:
        _require(draft.entities, to_id, "entity")

    data = draft.model_dump(by_alias=True)
    for relationship in data["relationships"]:
        if relationship["id"] != relationship_id:
            continue
        if from_id is not None:
            relationship["from"] = from_id
        if to_id is not None:
            relationship["to"] = to_id
        if relationship_type is not None:
            relationship["type"] = relationship_type
        if label is not None:
            relationship["label"] = label or None
        if cardinality is not None:
            relationship["cardinality"] = cardinality or None

    return EditOutcome(draft=CPMDraft.model_validate(data), summary="Updated relationship")


def set_use_case_actors(draft: CPMDraft, use_case_id: str, actor_ids: list[str]) -> EditOutcome:
    _require(draft.use_cases, use_case_id, "use case")
    for actor_id in actor_ids:
        _require(draft.actors, actor_id, "actor")

    data = draft.model_dump(by_alias=True)
    for use_case in data["useCases"]:
        if use_case["id"] == use_case_id:
            use_case["actors"] = list(dict.fromkeys(actor_ids))

    return EditOutcome(draft=CPMDraft.model_validate(data), summary="Updated actors")
