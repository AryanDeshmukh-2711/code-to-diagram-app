"""Running the margin query, and printing it so it can be read.

The prices are spliced in from the tier configuration rather than hard-coded
into the SQL, so changing a price in `tiers.json` changes what the report says
the next time it runs. That is the whole point of NFR-M4 from day one: the
numbers in the PRD are guesses, and the report exists to tell you which of
them are wrong before the pricing page does.
"""

from dataclasses import dataclass
from decimal import Decimal
from pathlib import Path
from typing import Any

from sqlalchemy import text

from billing.tiers import load_tiers
from store.session import SessionFactory

QUERY_PATH = Path(__file__).resolve().parent / "margin.sql"


@dataclass(frozen=True)
class MarginRow:
    tier: str
    runs: int
    active_accounts: int
    median_cost_per_run: Decimal
    mean_cost_per_run: Decimal
    p90_cost_per_run: Decimal
    total_inference_cost: Decimal
    price_per_account: Decimal
    revenue: Decimal
    gross_margin: Decimal
    margin_pct: Decimal | None
    runs_until_breakeven: Decimal | None
    median_duration_ms: Decimal | None
    total_tokens: int


def build_query(months: int = 1) -> str:
    """The SQL with the configured prices spliced in."""
    book = load_tiers()
    prices = ", ".join(f"('{tier.id}', {tier.monthly_price}::numeric)" for tier in book.tiers)
    return QUERY_PATH.read_text(encoding="utf-8").replace("{tier_prices}", prices)


async def margin_report(months: int = 1, session_factory=SessionFactory) -> list[MarginRow]:
    async with session_factory() as session:
        result = await session.execute(text(build_query(months)), {"months": months})
        return [MarginRow(**dict(row)) for row in result.mappings()]


def render(rows: list[MarginRow], months: int = 1) -> str:
    book = load_tiers()
    period = "this month" if months == 1 else f"the last {months} months"
    lines = [
        f"Margin per tier, {period}  (currency: {book.currency})",
        "",
        f"{'tier':<10}{'runs':>6}{'accts':>7}{'median/run':>13}{'mean/run':>11}"
        f"{'p90/run':>10}{'cost':>10}{'revenue':>10}{'margin':>10}{'margin%':>9}"
        f"{'breakeven':>11}",
        "-" * 107,
    ]
    if not rows:
        lines.append("  no succeeded runs recorded against a tier in this window")
        return "\n".join(lines)

    for row in rows:
        breakeven = (
            f"{int(row.runs_until_breakeven)} runs"
            if row.runs_until_breakeven is not None
            else ("free" if row.price_per_account == 0 else "n/a")
        )
        lines.append(
            f"{row.tier:<10}{row.runs:>6}{row.active_accounts:>7}"
            f"{row.median_cost_per_run:>13}{row.mean_cost_per_run:>11}"
            f"{row.p90_cost_per_run:>10}{row.total_inference_cost:>10}"
            f"{row.revenue:>10}{row.gross_margin:>10}"
            f"{('' if row.margin_pct is None else row.margin_pct):>9}"
            f"{breakeven:>11}"
        )

    lines.append("")
    lines.append(
        "median, not mean: inference cost per run is long tailed, and pricing "
        "against a mean prices against a customer who does not exist."
    )
    return "\n".join(lines)


def as_dicts(rows: list[MarginRow]) -> list[dict[str, Any]]:
    return [
        {
            key: (str(value) if isinstance(value, Decimal) else value)
            for key, value in row.__dict__.items()
        }
        for row in rows
    ]


if __name__ == "__main__":  # pragma: no cover - operational entry point
    import argparse
    import asyncio

    parser = argparse.ArgumentParser(description="Margin per tier (NFR-M4)")
    parser.add_argument("--months", type=int, default=1)
    parser.add_argument("--sql", action="store_true", help="print the query and exit")
    args = parser.parse_args()

    if args.sql:
        print(build_query(args.months))
    else:
        print(render(asyncio.run(margin_report(args.months)), args.months))
