"""The funnel, and the one number that must not be misread.

Most of these tests are about the review gate. Zero edits means either "the
extractor was right" or "nobody looked", and a metric that cannot separate
them is worse than none — it reads as good news in both cases. The classifier
is tested at its boundaries and with the pathological cases that would let one
answer masquerade as the other.
"""

from datetime import UTC, datetime, timedelta

import pytest

from analytics import events
from analytics.dashboard import render
from analytics.metrics import collect
from analytics.review_signals import (
    EDITED,
    RUBBER_STAMPED,
    UNKNOWN,
    VERIFIED,
    ReviewSignals,
    interpret,
)
from store.models import EventRow


def signals(**kwargs) -> ReviewSignals:
    base = dict(items_total=20, items_viewed=20, active_seconds=120.0)
    return ReviewSignals(**{**base, **kwargs})


# --------------------------------------------------------------------------
# The classifier
# --------------------------------------------------------------------------


def test_any_edit_means_the_gate_did_its_job() -> None:
    assert signals(edits_total=1, active_seconds=2.0, items_viewed=1).verdict == EDITED


def test_zero_edits_after_real_inspection_is_evidence_the_extractor_is_good() -> None:
    verdict = signals(edits_total=0, items_viewed=18, active_seconds=90.0).verdict
    assert verdict == VERIFIED
    assert "extractor is good" in interpret(verdict)


def test_zero_edits_without_inspection_is_a_product_problem() -> None:
    verdict = signals(edits_total=0, items_viewed=2, active_seconds=6.0).verdict
    assert verdict == RUBBER_STAMPED
    assert "decorative" in interpret(verdict)


def test_the_two_zero_edit_cases_are_told_apart() -> None:
    """The whole design, in one assertion.

    Identical outcome — no edits, model confirmed — and opposite verdicts,
    decided by evidence of attention rather than by the outcome.
    """
    attentive = signals(edits_total=0, items_viewed=20, active_seconds=150.0)
    hasty = signals(edits_total=0, items_viewed=1, active_seconds=4.0)

    assert attentive.edits_total == hasty.edits_total == 0
    assert attentive.verdict != hasty.verdict


def test_time_alone_cannot_buy_a_verified_verdict() -> None:
    # A screen left open over lunch is not a review. Coverage has to hold too.
    idle = signals(edits_total=0, items_viewed=1, active_seconds=3600.0)
    assert idle.verdict == RUBBER_STAMPED


def test_coverage_alone_cannot_buy_one_either() -> None:
    # Scrolling to the bottom in two seconds views every item and reads none.
    scrolled = signals(edits_total=0, items_viewed=20, active_seconds=2.0)
    assert scrolled.verdict == RUBBER_STAMPED


def test_the_time_bar_scales_with_the_size_of_the_model() -> None:
    """Twenty seconds is attentive for three entities and derisory for forty.

    A fixed threshold would flatter big models and punish small ones, which is
    exactly backwards.
    """
    small = ReviewSignals(items_total=3, items_viewed=3, active_seconds=20.0)
    large = ReviewSignals(items_total=40, items_viewed=40, active_seconds=20.0)

    assert small.verdict == VERIFIED
    assert large.verdict == RUBBER_STAMPED
    assert large.expected_seconds > small.expected_seconds


def test_a_screen_that_sent_nothing_is_its_own_bucket() -> None:
    # Not evidence either way, and not quietly counted as inattention: an
    # unmeasured confirmation would otherwise inflate the alarming number.
    assert ReviewSignals(edits_total=0).verdict == UNKNOWN
    assert "not evidence" in interpret(UNKNOWN)


def test_the_event_stores_the_raw_signals_beside_the_verdict() -> None:
    # So six months of history can be re-classified when the thresholds are
    # validated against real users, instead of being frozen at today's guess.
    payload = signals(edits_total=0, items_viewed=14).as_payload()
    for key in ("activeSeconds", "itemsViewed", "itemsTotal", "coverage", "attentionRatio"):
        assert key in payload
    assert payload["verdict"] == ReviewSignals.from_payload(payload).verdict


def test_a_payload_round_trips() -> None:
    original = signals(edits_total=2, edits_by_op={"rename_entity": 2}, inspections=9)
    assert ReviewSignals.from_payload(original.as_payload()).as_payload() == original.as_payload()


# --------------------------------------------------------------------------
# The funnel
# --------------------------------------------------------------------------


async def _event(session_factory, name, account, when=None, **payload) -> None:
    async with session_factory() as session:
        await events.record(
            session,
            name,
            account_id=account,
            run_id=payload.pop("run_id", None),
            payload=payload,
            occurred_at=when,
        )
        await session.commit()


def scoped(session_factory, schema: str):
    from contextlib import asynccontextmanager

    from sqlalchemy import text

    @asynccontextmanager
    async def factory():
        async with session_factory() as session:
            await session.execute(text(f"SET search_path TO {schema}"))
            yield session

    return factory


@pytest.fixture
async def funnel(session_factory):
    """Five accounts that get progressively further."""
    start = datetime.now(UTC) - timedelta(hours=2)
    for index in range(5):
        account = f"acct-{index}"
        await _event(session_factory, events.SIGNUP, account, start)
        if index >= 1:
            await _event(session_factory, events.PROJECT_CREATED, account, start)
        if index >= 2:
            await _event(
                session_factory,
                events.CPM_CONFIRMED,
                account,
                start,
                **ReviewSignals(
                    edits_total=index - 2,
                    items_total=20,
                    items_viewed=20 if index > 2 else 1,
                    active_seconds=120.0 if index > 2 else 3.0,
                ).as_payload(),
            )
        if index >= 3:
            await _event(session_factory, events.RUN_STARTED, account, start, run_id=f"r{index}")
        if index >= 4:
            await _event(
                session_factory,
                events.EXPORT_COMPLETED,
                account,
                start + timedelta(minutes=6),
                run_id=f"r{index}",
                format="pdf",
            )
    return session_factory


async def test_every_funnel_step_and_its_drop_off_is_visible(
    funnel, session_factory, db_schema
) -> None:
    metrics = await collect(session_factory=scoped(session_factory, db_schema))
    counts = {step.name: step.accounts for step in metrics.funnel}

    assert counts == {
        events.SIGNUP: 5,
        events.PROJECT_CREATED: 4,
        events.CPM_CONFIRMED: 3,
        events.RUN_STARTED: 2,
        events.EXPORT_COMPLETED: 1,
    }
    drops = {step.name: step.dropped for step in metrics.funnel}
    assert drops[events.EXPORT_COMPLETED] == 1
    assert metrics.funnel[-1].from_start_pct == 20.0


async def test_time_to_first_export_is_measured(funnel, session_factory, db_schema) -> None:
    metrics = await collect(session_factory=scoped(session_factory, db_schema))
    assert metrics.time_to_first_export["accounts"] == 1
    assert 300 <= float(metrics.time_to_first_export["median_seconds"]) <= 400


async def test_the_edit_distribution_is_visible(funnel, session_factory, db_schema) -> None:
    metrics = await collect(session_factory=scoped(session_factory, db_schema))
    distribution = {row["edits"]: row["confirmations"] for row in metrics.edit_distribution}
    assert distribution[0] == 1
    assert sum(distribution.values()) == 3


async def test_the_review_split_separates_the_two_zero_edit_cases(
    funnel, session_factory, db_schema
) -> None:
    metrics = await collect(session_factory=scoped(session_factory, db_schema))
    buckets = {row["verdict"]: row["confirmations"] for row in metrics.review["buckets"]}

    assert buckets[RUBBER_STAMPED] == 1, "the hasty confirmation is visible on its own"
    assert buckets[VERIFIED] == 0
    assert buckets[EDITED] == 2
    assert metrics.review["total"] == 3


async def test_a_run_that_was_regenerated_is_not_a_clean_export(session_factory, db_schema) -> None:
    await _event(session_factory, events.EXPORT_COMPLETED, "a", run_id="run-1")
    await _event(session_factory, events.EXPORT_COMPLETED, "b", run_id="run-2")
    await _event(
        session_factory, "regeneration_requested", "a", run_id="child", parentRunId="run-1"
    )

    metrics = await collect(session_factory=scoped(session_factory, db_schema))
    clean = metrics.clean_export_rate
    assert clean["exported_runs"] == 2
    assert clean["clean_runs"] == 1
    assert float(clean["clean_pct"]) == 50.0


async def test_the_dashboard_renders_without_a_third_party_script(
    funnel, session_factory, db_schema
) -> None:
    page = render(await collect(session_factory=scoped(session_factory, db_schema)))

    assert "<script" not in page.lower(), "the dashboard must not load a script"
    for marker in ("http://", "https://", "//cdn", "googletagmanager", "segment", "posthog"):
        assert marker not in page, f"the dashboard reaches out to {marker}"

    assert "Confirmed without inspecting" in page
    assert "Edits before confirming" in page
    assert "target &ge; 60%" in page


async def test_recording_an_event_never_breaks_the_request(session_factory) -> None:
    # Instrumentation that can fail a request is worse than no instrumentation.
    class Broken:
        def add(self, _row):
            raise RuntimeError("table is locked")

        async def flush(self):
            raise RuntimeError("table is locked")

    row = await events.record(Broken(), events.SIGNUP, account_id="a")
    assert isinstance(row, EventRow)


# --------------------------------------------------------------------------
# NFR-S2 / NFR-S4, pinned so the fix cannot regress
# --------------------------------------------------------------------------


def test_identity_is_read_in_exactly_one_place() -> None:
    """No endpoint may take the caller's identity from a request body.

    That was the pre-launch finding: `accountId` arrived in the body, so a
    caller could name any account and be believed. Identity now enters through
    one dependency; a body field named like an identity is the regression.
    """
    import ast
    from pathlib import Path

    routers = Path(__file__).resolve().parents[2] / "api" / "app" / "routers"
    for path in routers.glob("*.py"):
        # auth.py is the exception, and the only one: /auth/token takes an
        # account id *with the key that proves it*. Everywhere else an account
        # id in a body is an assertion the server would have to take on trust.
        if path.name == "auth.py":
            continue
        tree = ast.parse(path.read_text(encoding="utf-8"))
        for node in ast.walk(tree):
            # Responses may name an account; requests may not.
            if not isinstance(node, ast.ClassDef) or node.name.endswith("Out"):
                continue
            fields = {
                target.target.id
                for target in node.body
                if isinstance(target, ast.AnnAssign) and isinstance(target.target, ast.Name)
            }
            leaked = fields & {"accountId", "account_id", "userId", "user_id"}
            assert not leaked, f"{path.name}:{node.name} takes identity from the body: {leaked}"


def test_every_run_and_project_route_proves_ownership() -> None:
    import ast
    from pathlib import Path

    routers = Path(__file__).resolve().parents[2] / "api" / "app" / "routers"
    unguarded = []
    for name in ("runs.py", "review.py", "exports.py", "extraction.py", "chat.py", "projects.py"):
        source = (routers / name).read_text(encoding="utf-8")
        tree = ast.parse(source)
        for node in ast.walk(tree):
            if not isinstance(node, ast.AsyncFunctionDef):
                continue
            decorated = any(
                isinstance(d, ast.Call)
                and getattr(d.func, "attr", "") in {"get", "post", "delete", "patch", "put"}
                for d in node.decorator_list
            )
            if not decorated or node.name in {
                "download_artefact",
                "download_export",
                "dashboard",
                "metrics_json",
                # Lists every template unconditionally — nothing here is
                # scoped to a project, run or any other owned resource.
                "list_templates",
            }:
                continue
            body = ast.unparse(node)
            if "require_account" not in ast.unparse(node.args):
                unguarded.append(f"{name}:{node.name} has no identity")
            elif not any(
                helper in body
                for helper in (
                    "owned_run",
                    "owned_project",
                    "owned_extraction",
                    "owned_chat_edit",
                    "ensure_project",
                    "_load",
                    "check_new",
                    "account_id",
                    "account_tier",
                )
            ):
                unguarded.append(f"{name}:{node.name} never checks ownership")
    assert not unguarded, "\n".join(unguarded)


def test_a_session_token_cannot_be_forged_or_reused_past_its_life() -> None:
    """The last High finding of the pre-launch review, pinned.

    Identity used to be a header the server believed. It is now a signature
    over the account and a deadline, minted only for a caller who holds the
    account's key.
    """
    identity = _identity_module()
    from fastapi import HTTPException

    key, stored, salt = identity.new_api_key()
    assert identity.verify_api_key(key, stored, salt)
    assert not identity.verify_api_key(key + "x", stored, salt)
    assert not identity.verify_api_key(key, None, None)

    token = identity.issue_session("acct-1", ttl_seconds=60)
    assert identity._decode(token) == "acct-1"

    with pytest.raises(HTTPException):
        identity._decode(token[:-4] + "AAAA")
    with pytest.raises(HTTPException) as expired:
        identity._decode(identity.issue_session("acct-1", ttl_seconds=-1))
    assert "expired" in expired.value.detail


def _identity_module():
    import importlib
    import os
    import sys
    from pathlib import Path

    sys.path.insert(0, str(Path(__file__).resolve().parents[2] / "api"))
    os.environ.setdefault("ASA_SIGNING_SECRET", "test-secret")
    identity = importlib.import_module("app.core.identity")
    identity.SECRET = b"test-secret"
    return identity


def test_a_signed_link_is_scoped_to_one_artefact_and_expires() -> None:
    identity = _identity_module()

    token = identity.sign("artefact-a", ttl_seconds=60)
    identity.verify("artefact-a", token)

    from fastapi import HTTPException

    with pytest.raises(HTTPException) as wrong_artefact:
        identity.verify("artefact-b", token)
    assert wrong_artefact.value.status_code == 403

    with pytest.raises(HTTPException) as expired:
        identity.verify("artefact-a", identity.sign("artefact-a", ttl_seconds=-1))
    assert "expired" in expired.value.detail
