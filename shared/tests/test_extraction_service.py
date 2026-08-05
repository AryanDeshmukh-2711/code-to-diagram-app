"""Extraction: normalised text -> valid CPM, or an honest refusal.

The single most important property here is negative: **the service never adds
anything the model did not return.** Risk R1 (rated High in the PRD) is a
plausible-but-wrong artefact reaching a submission, and its source is exactly
here — a pipeline that pads a thin model to clear a completeness floor produces
something that looks finished and is fiction. Returning "your description is
too vague, add X" is the correct outcome, and it is asserted below.
"""

import copy
import json
import random
from datetime import UTC, datetime

import pytest
from extraction_samples import BY_KEY, SAMPLES, VAGUE

from cpm.schema import CPM
from extraction import Extracted, ExtractionService, InsufficientInput
from llm.config import TaskConfig
from llm.gateway import LLMGateway
from llm.providers.scripted import ScriptedProvider

FIXED_TIME = datetime(2026, 7, 30, tzinfo=UTC)

TASK = TaskConfig(
    provider="scripted",
    model="stub-model",
    max_tokens=8192,
    temperature=0.0,
    timeout_seconds=60.0,
    system_prompt="Extract a project model.",
)


def service_returning(payload: dict) -> ExtractionService:
    gateway = LLMGateway(
        providers={"scripted": ScriptedProvider([json.dumps(payload)])},
        tasks={"cpm_extraction": TASK},
    )
    return ExtractionService(gateway)


async def run(sample_key: str, *, payload: dict | None = None):
    sample = BY_KEY[sample_key]
    service = service_returning(payload if payload is not None else sample.llm_output)
    return await service.extract(
        sample.description, project_name="Test Project", created_at=FIXED_TIME
    )


# --------------------------------------------------------------------------
# The floor (FR-5) — and the refusal to fabricate
# --------------------------------------------------------------------------


async def test_vague_input_returns_insufficient_rather_than_a_model() -> None:
    result = await run("vague_startup")
    assert isinstance(result, InsufficientInput)


async def test_the_vague_sample_is_long_enough_for_the_floor_to_apply() -> None:
    # If it were 20 words, length alone would reject it and the test would be
    # proving nothing about fabrication.
    assert VAGUE.word_count >= 200


async def test_insufficient_reports_what_it_actually_found() -> None:
    result = await run("vague_startup")
    assert isinstance(result, InsufficientInput)
    assert result.entities_found == 1
    assert result.relationships_found == 0
    assert result.word_count >= 200


async def test_insufficient_says_specifically_what_to_add() -> None:
    # "Insufficient input" on its own leaves the user stuck. The guidance has
    # to name what is missing.
    result = await run("vague_startup")
    assert isinstance(result, InsufficientInput)
    assert result.guidance
    joined = " ".join(result.guidance).lower()
    assert "entit" in joined or "thing" in joined
    assert "relationship" in joined or "relate" in joined


async def test_nothing_is_invented_to_clear_the_floor() -> None:
    # The failure mode this whole test module exists for: topping up a thin
    # model with plausible-sounding entities so the run "succeeds".
    result = await run("vague_startup")
    assert isinstance(result, InsufficientInput)
    assert result.entities_found == len(VAGUE.llm_output["entities"])


async def test_a_long_input_with_two_entities_still_fails_the_floor() -> None:
    payload = copy.deepcopy(VAGUE.llm_output)
    payload["entities"] = [
        {"id": "user", "name": "User"},
        {"id": "workspace", "name": "Workspace"},
    ]
    payload["relationships"] = [
        {"id": "r1", "from": "user", "to": "workspace", "type": "association"}
    ]
    result = await run("vague_startup", payload=payload)
    assert isinstance(result, InsufficientInput), (
        "FR-5 requires >= 3 entities and >= 2 relationships"
    )


async def test_relationship_guidance_names_the_entities_actually_found() -> None:
    # A fixed "a member borrows loans" example means nothing to someone whose
    # description was never about a library. Once two or more entities exist,
    # the guidance has to ask about them by name — the same entities the
    # reason line above it already reported finding.
    payload = copy.deepcopy(VAGUE.llm_output)
    payload["entities"] = [
        {"id": "project", "name": "Project"},
        {"id": "diagram", "name": "Diagram"},
        {"id": "document", "name": "Document"},
    ]
    payload["relationships"] = []
    result = await run("vague_startup", payload=payload)
    assert isinstance(result, InsufficientInput)
    relationship_line = next(line for line in result.guidance if "connect" in line)
    assert "Project" in relationship_line
    assert "Diagram" in relationship_line
    assert "member" not in relationship_line.lower()
    assert "loan" not in relationship_line.lower()


async def test_relationship_guidance_falls_back_with_fewer_than_two_entities() -> None:
    # Nothing to name yet -- the generic example is still the honest answer.
    result = await run("vague_startup")
    assert isinstance(result, InsufficientInput)
    joined = " ".join(result.guidance).lower()
    assert "member" in joined and "loan" in joined


async def test_an_empty_model_is_insufficient_regardless_of_length() -> None:
    payload = {k: [] for k in VAGUE.llm_output}
    result = await run("parking_lot", payload=payload)
    assert isinstance(result, InsufficientInput)


async def test_a_short_but_concrete_description_is_accepted() -> None:
    # Under 200 words, so the FR-5 floor does not apply. Rejecting this would
    # be over-correction: it describes a real system in few words.
    sample = BY_KEY["parking_lot"]
    assert sample.word_count < 200
    assert isinstance(await run("parking_lot"), Extracted)


# --------------------------------------------------------------------------
# The service adds nothing — across every sample
# --------------------------------------------------------------------------


@pytest.mark.parametrize("sample", SAMPLES, ids=lambda s: s.key)
async def test_no_entity_appears_that_the_model_did_not_return(sample) -> None:
    from extraction.normalise import canonical_name_key

    result = await run(sample.key)
    if isinstance(result, InsufficientInput):
        return

    produced = {canonical_name_key(e.name) for e in result.cpm.entities}
    returned = {canonical_name_key(e["name"]) for e in sample.llm_output["entities"]}
    assert produced <= returned, f"invented: {produced - returned}"


@pytest.mark.parametrize("sample", SAMPLES, ids=lambda s: s.key)
async def test_no_actor_appears_that_the_model_did_not_return(sample) -> None:
    from extraction.normalise import canonical_name_key

    result = await run(sample.key)
    if isinstance(result, InsufficientInput):
        return

    produced = {canonical_name_key(a.name) for a in result.cpm.actors}
    returned = {canonical_name_key(a["name"]) for a in sample.llm_output["actors"]}
    assert produced <= returned


@pytest.mark.parametrize("sample", SAMPLES, ids=lambda s: s.key)
async def test_every_sample_yields_a_valid_cpm_or_an_honest_refusal(sample) -> None:
    result = await run(sample.key)
    if isinstance(result, Extracted):
        assert isinstance(result.cpm, CPM)
    else:
        assert isinstance(result, InsufficientInput)
        assert result.reason


# --------------------------------------------------------------------------
# Normalisation: merge duplicates, drop orphans
# --------------------------------------------------------------------------


async def test_near_identical_entity_names_collapse_to_one() -> None:
    # Patient / Patients / patient are one concept spelled three ways.
    result = await run("clinic_appointments")
    assert isinstance(result, Extracted)

    patients = [e for e in result.cpm.entities if e.name.lower().startswith("patient")]
    assert len(patients) == 1
    assert patients[0].name == "Patient"


async def test_merging_keeps_the_attributes_of_every_duplicate() -> None:
    # Merging must not silently discard the fields the duplicates carried —
    # that would be data loss dressed up as tidying.
    result = await run("clinic_appointments")
    assert isinstance(result, Extracted)

    patient = next(e for e in result.cpm.entities if e.name == "Patient")
    names = {attribute.name for attribute in patient.attributes}
    assert {"patientId", "name", "dateOfBirth", "phoneNumber"} <= names


async def test_references_to_a_merged_entity_are_repointed_not_dropped() -> None:
    result = await run("clinic_appointments")
    assert isinstance(result, Extracted)

    # `r-patients-invoice` pointed at the merged-away "patients".
    repointed = next(r for r in result.cpm.relationships if r.id == "r-patients-invoice")
    assert repointed.from_ == "patient"


async def test_an_orphan_relationship_is_dropped_not_given_an_invented_endpoint() -> None:
    result = await run("clinic_appointments")
    assert isinstance(result, Extracted)

    ids = {r.id for r in result.cpm.relationships}
    assert "r-orphan-lab" not in ids
    assert not any(e.id == "lab-test" for e in result.cpm.entities), "endpoint must not be invented"


async def test_a_use_case_actor_that_was_never_declared_is_dropped() -> None:
    result = await run("clinic_appointments")
    assert isinstance(result, Extracted)

    use_case = next(u for u in result.cpm.use_cases if u.id == "uc-book-appointment")
    assert "nurse" not in use_case.actors
    assert not any(a.id == "nurse" for a in result.cpm.actors)


async def test_a_state_on_an_undeclared_entity_is_dropped() -> None:
    result = await run("clinic_appointments")
    assert isinstance(result, Extracted)
    assert not any(s.id == "s-labtest-pending" for s in result.cpm.states)


async def test_a_transition_to_an_unknown_state_is_dropped() -> None:
    result = await run("clinic_appointments")
    assert isinstance(result, Extracted)

    booked = next(s for s in result.cpm.states if s.id == "s-appt-booked")
    assert {t.to for t in booked.transitions} == {"s-appt-completed"}


async def test_a_slug_shaped_requires_entry_is_canonicalised_to_the_components_name() -> None:
    result = await run("library_management")
    assert isinstance(result, Extracted)

    lending = next(c for c in result.cpm.components if c.id == "comp-lending")
    assert lending.requires == ["Catalogue Service"]


async def test_an_undeclared_deployed_component_is_dropped() -> None:
    result = await run("clinic_appointments")
    assert isinstance(result, Extracted)

    node = next(n for n in result.cpm.nodes if n.id == "node-desk")
    assert node.deployed_components == []


async def test_a_flow_participant_that_is_neither_actor_nor_entity_is_dropped() -> None:
    result = await run("clinic_appointments")
    assert isinstance(result, Extracted)

    flow = next(f for f in result.cpm.flows if f.id == "flow-consultation")
    assert "pharmacy" not in flow.participants
    # ...and the step that addressed it goes with it, rather than dangling.
    assert all(step.to in flow.participants for step in flow.steps)
    assert all(step.from_ in flow.participants for step in flow.steps)


async def test_lowercase_names_are_title_cased() -> None:
    result = await run("clinic_appointments")
    assert isinstance(result, Extracted)

    assert any(a.name == "Receptionist" for a in result.cpm.actors)
    assert any(e.name == "Appointment" for e in result.cpm.entities)


async def test_normalisation_is_reported_rather_than_done_silently() -> None:
    # The review gate has to be able to tell the user what was changed on their
    # behalf; silent edits are how a user signs off on something they never saw.
    result = await run("clinic_appointments")
    assert isinstance(result, Extracted)

    notes = " ".join(result.notes).lower()
    assert "merged" in notes
    assert "dropped" in notes


# --------------------------------------------------------------------------
# Deterministic ordering
# --------------------------------------------------------------------------


async def test_arrays_are_sorted_deterministically() -> None:
    result = await run("library_management")
    assert isinstance(result, Extracted)

    cpm = result.cpm
    assert [e.id for e in cpm.entities] == sorted(e.id for e in cpm.entities)
    assert [a.id for a in cpm.actors] == sorted(a.id for a in cpm.actors)
    assert [u.id for u in cpm.use_cases] == sorted(u.id for u in cpm.use_cases)
    assert [c.id for c in cpm.components] == sorted(c.id for c in cpm.components)
    assert [n.id for n in cpm.nodes] == sorted(n.id for n in cpm.nodes)
    assert [r.id for r in cpm.requirements] == sorted(r.id for r in cpm.requirements)


async def test_the_same_input_produces_byte_identical_output() -> None:
    first = await run("library_management")
    second = await run("library_management")
    assert isinstance(first, Extracted) and isinstance(second, Extracted)
    assert first.cpm.model_dump_json(by_alias=True) == second.cpm.model_dump_json(by_alias=True)


async def test_shuffling_the_model_output_does_not_change_the_result() -> None:
    # The real determinism test. An LLM emits collections in whatever order it
    # likes across runs; if that leaked through, every re-extraction would show
    # a diff even when nothing changed.
    baseline = await run("library_management")
    assert isinstance(baseline, Extracted)

    shuffled = copy.deepcopy(BY_KEY["library_management"].llm_output)
    rng = random.Random(20260730)
    for value in shuffled.values():
        if isinstance(value, list):
            rng.shuffle(value)

    result = await run("library_management", payload=shuffled)
    assert isinstance(result, Extracted)
    assert result.cpm.model_dump_json(by_alias=True) == baseline.cpm.model_dump_json(by_alias=True)


async def test_attributes_are_ordered_with_keys_first_then_alphabetically() -> None:
    # Sorted for diffability, but key-first because a class diagram that leads
    # with the primary key reads correctly.
    result = await run("library_management")
    assert isinstance(result, Extracted)

    book = next(e for e in result.cpm.entities if e.name == "Book")
    assert [a.name for a in book.attributes] == [
        "isbn",
        "author",
        "copies",
        "publicationYear",
        "title",
    ]


async def test_flow_steps_stay_in_their_own_order_not_alphabetical() -> None:
    # Sorting a sequence diagram's steps by anything but `order` would be
    # deterministic and wrong.
    result = await run("library_management")
    assert isinstance(result, Extracted)

    flow = result.cpm.flows[0]
    assert [s.order for s in flow.steps] == sorted(s.order for s in flow.steps)


async def test_prose_lists_are_left_in_the_order_the_model_wrote_them() -> None:
    result = await run("library_management")
    assert isinstance(result, Extracted)

    use_case = next(u for u in result.cpm.use_cases if u.id == "uc-borrow-book")
    assert use_case.main_flow == [
        "The librarian scans the book.",
        "The system creates a loan.",
    ]


# --------------------------------------------------------------------------
# Metadata
# --------------------------------------------------------------------------


async def test_the_caller_supplies_project_name_and_timestamp() -> None:
    # Neither is something the model should be guessing at.
    result = await run("library_management")
    assert isinstance(result, Extracted)
    assert result.cpm.meta.project_name == "Test Project"
    assert result.cpm.meta.created_at == FIXED_TIME
