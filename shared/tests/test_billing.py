"""Tiers, quotas and margin.

Two things carry the weight. Enforcement has to be server side — a limit the
browser respects is a limit only for people who use the browser — so the
checks here run against a real database and a separate test asserts the API
routes actually call them. And the margin query has to compute what it claims:
its numbers are checked against a deliberately skewed cost distribution, where
a mean and a median disagree, because that disagreement is the whole reason
the query uses a median.
"""

import ast
import json
from datetime import UTC, datetime
from decimal import Decimal
from pathlib import Path

import pytest
from sqlalchemy import text

from billing.margin import build_query, margin_report, render
from billing.quota import (
    QuotaExceeded,
    account_tier,
    check_export,
    check_new_project,
    check_new_run,
    check_template,
)
from billing.tiers import CONFIG_PATH, UnknownTier, load_tiers
from store.models import AccountRow, GenerationRunRow, ProjectRow, RunStatus

API = Path(__file__).resolve().parents[2] / "api" / "app" / "routers"


# --------------------------------------------------------------------------
# Configuration
# --------------------------------------------------------------------------


def test_the_prd_tiers_are_configured_not_coded() -> None:
    book = load_tiers()
    assert [tier.id for tier in book.tiers] == ["free", "student", "pro"]

    free, student, pro = book.tiers
    assert free.max_projects == 2
    assert free.watermark is True
    assert free.exports == ("pdf",)
    assert free.diagram_formats == ("png",)
    assert student.max_projects is None, "unlimited is spelt null, not a big number"
    assert student.watermark is False
    assert set(student.exports) == {"pdf", "docx"}
    assert student.custom_template is True
    assert pro.queue == "priority"


def test_a_limit_changes_without_a_deploy(tmp_path, monkeypatch) -> None:
    """The DoD, at its narrowest: edit the file, the limit moves."""
    payload = json.loads(CONFIG_PATH.read_text(encoding="utf-8"))
    payload["tiers"][0]["max_projects"] = 7
    payload["tiers"][0]["monthly_price"] = "1.50"
    path = tmp_path / "tiers.json"
    path.write_text(json.dumps(payload), encoding="utf-8")

    monkeypatch.setattr("billing.tiers.CONFIG_PATH", path)
    free = load_tiers().get("free")
    assert free.max_projects == 7
    assert free.monthly_price == Decimal("1.50")
    # And the margin query prices from the same file.
    assert "1.50" in build_query()


def test_an_unknown_tier_is_refused_with_the_known_ones() -> None:
    with pytest.raises(UnknownTier, match="free, student, pro"):
        load_tiers().get("enterprise")


def test_the_config_is_read_per_call_not_cached_at_import(tmp_path, monkeypatch) -> None:
    payload = json.loads(CONFIG_PATH.read_text(encoding="utf-8"))
    path = tmp_path / "tiers.json"
    path.write_text(json.dumps(payload), encoding="utf-8")
    monkeypatch.setattr("billing.tiers.CONFIG_PATH", path)

    assert load_tiers().get("free").max_projects == 2
    payload["tiers"][0]["max_projects"] = 99
    path.write_text(json.dumps(payload), encoding="utf-8")
    assert load_tiers().get("free").max_projects == 99


# --------------------------------------------------------------------------
# Enforcement
# --------------------------------------------------------------------------


async def _account(session_factory, tier: str = "free", account_id: str = "acct") -> str:
    async with session_factory() as session:
        session.add(AccountRow(id=account_id, tier=tier))
        await session.commit()
    return account_id


async def _projects(session_factory, account_id: str, count: int) -> None:
    async with session_factory() as session:
        for index in range(count):
            session.add(ProjectRow(id=f"p{index}", account_id=account_id, name=f"P{index}"))
        await session.commit()


async def test_the_free_project_limit_is_enforced(session_factory) -> None:
    account = await _account(session_factory)
    await _projects(session_factory, account, 2)

    async with session_factory() as session:
        with pytest.raises(QuotaExceeded) as excinfo:
            await check_new_project(session, account)

    refusal = excinfo.value.refusal
    assert refusal.code == "project_limit"
    assert refusal.limit == 2 and refusal.used == 2
    assert refusal.upgrade_to == "student"


async def test_the_refusal_tells_the_user_what_to_do_and_does_not_scold(
    session_factory,
) -> None:
    account = await _account(session_factory)
    await _projects(session_factory, account, 2)

    async with session_factory() as session:
        with pytest.raises(QuotaExceeded) as excinfo:
            await check_new_project(session, account)

    message = excinfo.value.refusal.message.lower()
    assert "delete one" in message
    assert "stays where it is" in message, "the user needs to know nothing was lost"
    for word in ("denied", "forbidden", "violation", "illegal", "not allowed", "error"):
        assert word not in message, f"the refusal says {word!r}"
    assert "unlimited projects" in excinfo.value.refusal.upgrade_gives


async def test_an_unlimited_tier_has_no_project_ceiling(session_factory) -> None:
    account = await _account(session_factory, "student")
    await _projects(session_factory, account, 40)
    async with session_factory() as session:
        assert (await check_new_project(session, account)).id == "student"


async def test_the_free_tier_cannot_ask_for_svg(session_factory) -> None:
    account = await _account(session_factory)
    async with session_factory() as session:
        assert (await check_new_run(session, account, "png")).id == "free"
        with pytest.raises(QuotaExceeded) as excinfo:
            await check_new_run(session, account, "svg")
    assert excinfo.value.refusal.code == "diagram_format"


async def test_export_entitlements_follow_the_tier(session_factory) -> None:
    free = await _account(session_factory, "free", "free-acct")
    student = await _account(session_factory, "student", "student-acct")

    async with session_factory() as session:
        assert await check_export(session, free, "pdf")
        with pytest.raises(QuotaExceeded) as excinfo:
            await check_export(session, free, "docx")
        assert await check_export(session, student, "docx")

    assert excinfo.value.refusal.code == "export_format"
    assert "already generated" in excinfo.value.refusal.message


async def test_a_restricted_tier_may_not_pick_any_template(session_factory) -> None:
    free = await _account(session_factory, "free", "f")
    pro = await _account(session_factory, "pro", "p")
    async with session_factory() as session:
        assert await check_template(session, free, "ieee-830-plain")
        with pytest.raises(QuotaExceeded):
            await check_template(session, free, "bound-project-report")
        assert await check_template(session, pro, "bound-project-report")


async def test_the_monthly_run_allowance_counts_this_month_only(session_factory) -> None:
    account = await _account(session_factory)
    limit = load_tiers().get("free").max_runs_per_month
    async with session_factory() as session:
        for index in range(limit):
            session.add(
                GenerationRunRow(
                    id=f"r{index}",
                    project_id="p",
                    cpm_version_id="v",
                    account_id=account,
                    tier="free",
                    requested_types=["class"],
                    status=RunStatus.SUCCEEDED,
                    created_at=datetime.now(UTC),
                )
            )
        # Last month's runs do not count against this month.
        session.add(
            GenerationRunRow(
                id="old",
                project_id="p",
                cpm_version_id="v",
                account_id=account,
                tier="free",
                requested_types=["class"],
                status=RunStatus.SUCCEEDED,
                created_at=datetime(2020, 1, 1, tzinfo=UTC),
            )
        )
        await session.commit()

        with pytest.raises(QuotaExceeded) as excinfo:
            await check_new_run(session, account, "png")

    assert excinfo.value.refusal.used == limit
    assert "resets on the first" in excinfo.value.refusal.message


async def test_an_unknown_account_gets_the_cheapest_tier(session_factory) -> None:
    async with session_factory() as session:
        assert (await account_tier(session, "nobody")).id == "free"


# --------------------------------------------------------------------------
# Server side, not UI side
# --------------------------------------------------------------------------


def test_the_api_routes_call_the_quota_service() -> None:
    """UI-only enforcement is trivially bypassed, so the routes must check.

    Asserted structurally rather than by reading a response: a route that
    stopped calling the service would still return 200 to every test that only
    exercised the happy path.
    """
    called: dict[str, set[str]] = {}
    for name in ("review.py", "runs.py"):
        tree = ast.parse((API / name).read_text(encoding="utf-8"))
        called[name] = {
            node.func.id
            for node in ast.walk(tree)
            if isinstance(node, ast.Call) and isinstance(node.func, ast.Name)
        }

    assert "check_new_project" in called["review.py"], "project creation is unguarded"
    assert "check_new_run" in called["runs.py"], "run creation is unguarded"
    assert "check_template" in called["runs.py"], "template choice is unguarded"


def test_no_route_offers_a_way_to_skip_the_check() -> None:
    forbidden = ("skip_quota", "skipQuota", "ignore_quota", "bypass_quota", "no_quota")
    for name in ("review.py", "runs.py"):
        source = (API / name).read_text(encoding="utf-8")
        for token in forbidden:
            assert token not in source, f"{name} offers {token}"


def test_a_refusal_carries_everything_a_client_needs_to_explain_it(session_factory) -> None:
    from billing.quota import QuotaRefusal

    payload = QuotaRefusal(
        code="project_limit",
        message="…",
        tier="free",
        limit=2,
        used=2,
        upgrade_to="student",
        upgrade_gives="Student ($5.00/month) includes unlimited projects",
    ).as_dict()

    assert set(payload) == {
        "code",
        "message",
        "tier",
        "limit",
        "used",
        "upgradeTo",
        "upgradeGives",
    }


# --------------------------------------------------------------------------
# NFR-M4: the margin query
# --------------------------------------------------------------------------


def scoped(session_factory, schema: str):
    """A factory whose sessions see the test schema.

    The margin report is raw SQL with unqualified table names, so SQLAlchemy's
    schema translation does not reach it — the search path has to be set on the
    connection instead.
    """
    from contextlib import asynccontextmanager

    @asynccontextmanager
    async def factory():
        async with session_factory() as session:
            await session.execute(text(f"SET search_path TO {schema}"))
            yield session

    return factory


SKEWED = ["0.01", "0.01", "0.02", "0.02", "0.03", "0.03", "0.04", "0.05", "0.06", "4.00"]
"""Nine ordinary runs and one enormous one. Median 0.03, mean 0.427 — a
fourteen-fold difference, which is exactly the case the query is shaped for."""


async def _seed_runs(session_factory, tier: str, costs: list[str], accounts: int = 2) -> None:
    async with session_factory() as session:
        for index, cost in enumerate(costs):
            session.add(
                GenerationRunRow(
                    id=f"{tier}-{index}",
                    project_id="p",
                    cpm_version_id="v",
                    account_id=f"{tier}-acct-{index % accounts}",
                    tier=tier,
                    requested_types=["class"],
                    status=RunStatus.SUCCEEDED,
                    created_at=datetime.now(UTC),
                    duration_ms=1000 + index,
                    llm_cost_usd=cost,
                    llm_input_tokens=100,
                    llm_output_tokens=50,
                )
            )
        await session.commit()


async def test_the_margin_query_reports_median_not_mean(session_factory, db_schema) -> None:
    await _seed_runs(session_factory, "student", SKEWED)
    rows = await margin_report(session_factory=scoped(session_factory, db_schema))

    student = next(row for row in rows if row.tier == "student")
    assert student.runs == 10
    assert student.active_accounts == 2
    assert student.median_cost_per_run == Decimal("0.030000")
    assert student.mean_cost_per_run == Decimal("0.427000")
    assert student.median_cost_per_run < student.mean_cost_per_run / 10


async def test_the_margin_query_prices_from_the_tier_config(session_factory, db_schema) -> None:
    await _seed_runs(session_factory, "student", SKEWED)
    rows = await margin_report(session_factory=scoped(session_factory, db_schema))
    student = next(row for row in rows if row.tier == "student")

    price = load_tiers().get("student").monthly_price
    assert student.price_per_account == price
    assert student.revenue == price * student.active_accounts
    assert student.gross_margin == student.revenue - student.total_inference_cost


async def test_breakeven_says_how_many_runs_a_subscription_buys(session_factory, db_schema) -> None:
    await _seed_runs(session_factory, "student", SKEWED)
    rows = await margin_report(session_factory=scoped(session_factory, db_schema))
    student = next(row for row in rows if row.tier == "student")

    # $5.00 a month against a median run of $0.03.
    assert student.runs_until_breakeven == Decimal("166")


async def test_a_free_tier_shows_cost_with_no_revenue(session_factory, db_schema) -> None:
    await _seed_runs(session_factory, "free", ["0.05", "0.05", "0.05"], accounts=3)
    rows = await margin_report(session_factory=scoped(session_factory, db_schema))
    free = next(row for row in rows if row.tier == "free")

    assert free.revenue == Decimal("0.00")
    assert free.total_inference_cost == Decimal("0.1500")
    assert free.gross_margin == Decimal("-0.15"), "the free tier costs money; say so"
    assert free.margin_pct is None


async def test_the_tier_on_the_run_survives_an_upgrade(session_factory, db_schema) -> None:
    # The point of storing the tier on the run: a student who upgrades must not
    # retroactively move September's free-plan costs onto the paid plan.
    await _seed_runs(session_factory, "free", ["0.10"], accounts=1)
    async with session_factory() as session:
        session.add(AccountRow(id="free-acct-0", tier="pro"))
        await session.commit()

    rows = await margin_report(session_factory=scoped(session_factory, db_schema))
    assert {row.tier for row in rows} == {"free"}


async def test_failed_runs_are_not_counted_against_margin(session_factory, db_schema) -> None:
    await _seed_runs(session_factory, "student", ["0.02"])
    async with session_factory() as session:
        session.add(
            GenerationRunRow(
                id="failed",
                project_id="p",
                cpm_version_id="v",
                account_id="student-acct-0",
                tier="student",
                requested_types=["class"],
                status=RunStatus.FAILED,
                created_at=datetime.now(UTC),
                llm_cost_usd="9.99",
            )
        )
        await session.commit()

    rows = await margin_report(session_factory=scoped(session_factory, db_schema))
    student = next(row for row in rows if row.tier == "student")
    assert student.runs == 1
    assert student.total_inference_cost == Decimal("0.0200")


async def test_the_report_renders_when_there_is_nothing_to_report(
    session_factory, db_schema
) -> None:
    rows = await margin_report(session_factory=scoped(session_factory, db_schema))
    assert "no succeeded runs" in render(rows)
