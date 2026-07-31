"""The dashboard: one server-rendered page, no analytics SDK.

Bars are divs. There is no charting library, no tracking script and no request
to anyone else's domain, which is why the numbers on this page are the numbers
in the database rather than the numbers that survived an ad blocker.

It is deliberately plain. This page exists to answer six questions and to make
one of them — how people behave at the review gate — impossible to misread.
"""

from html import escape
from typing import Any

from analytics.metrics import Metrics

STEP_LABELS = {
    "signup": "Signed up",
    "project_created": "Created a project",
    "cpm_confirmed": "Confirmed the model",
    "run_started": "Generated",
    "export_completed": "Exported",
}

VERDICT_LABELS = {
    "edited": "Edited the model",
    "verified": "Confirmed after inspecting",
    "rubber_stamped": "Confirmed without inspecting",
    "unknown": "No attention signal",
}

VERDICT_COLOURS = {
    "edited": "#2f6f4e",
    "verified": "#2c5aa0",
    "rubber_stamped": "#a33",
    "unknown": "#888",
}

CSS = """
:root { color-scheme: light dark; }
body { font: 15px/1.5 -apple-system, Segoe UI, Roboto, sans-serif; margin: 0;
       padding: 32px; max-width: 1000px; }
h1 { font-size: 22px; margin: 0 0 4px; }
h2 { font-size: 15px; text-transform: uppercase; letter-spacing: .06em;
     margin: 36px 0 10px; opacity: .65; }
.sub { opacity: .6; margin: 0 0 8px; }
table { border-collapse: collapse; width: 100%; }
th, td { text-align: left; padding: 7px 10px; border-bottom: 1px solid #8884; }
th { font-weight: 600; font-size: 13px; opacity: .7; }
td.n, th.n { text-align: right; font-variant-numeric: tabular-nums; }
.bar { height: 12px; border-radius: 2px; background: #2c5aa0; min-width: 2px; }
.track { background: #8882; border-radius: 2px; }
.drop { color: #a33; font-size: 13px; }
.note { font-size: 13px; opacity: .7; margin-top: 6px; }
.target-hit { color: #2f6f4e; font-weight: 600; }
.target-miss { color: #a33; font-weight: 600; }
.big { font-size: 26px; font-variant-numeric: tabular-nums; }
.card { border: 1px solid #8884; border-radius: 8px; padding: 14px 16px; }
.cards { display: flex; gap: 12px; flex-wrap: wrap; }
.cards .card { flex: 1 1 190px; }
"""


def _fmt(value: Any, digits: int = 0, dash: str = "—") -> str:
    if value is None:
        return dash
    try:
        number = float(value)
    except (TypeError, ValueError):
        return escape(str(value))
    return f"{number:,.{digits}f}"


def _duration(seconds: Any) -> str:
    if seconds is None:
        return "—"
    seconds = float(seconds)
    if seconds < 90:
        return f"{seconds:.0f}s"
    if seconds < 5400:
        return f"{seconds / 60:.1f} min"
    return f"{seconds / 3600:.1f} h"


def _bar(value: float, maximum: float, colour: str = "#2c5aa0") -> str:
    width = 0 if not maximum else max(1, round(100 * value / maximum))
    return (
        f'<div class="track"><div class="bar" style="width:{width}%;'
        f'background:{colour}"></div></div>'
    )


def render(metrics: Metrics) -> str:
    parts = [
        f"<style>{CSS}</style>",
        "<h1>Funnel and product metrics</h1>",
        f'<p class="sub">Last {metrics.days} days · PRD section 9 · '
        f"derived from the event log, not from counters</p>",
    ]

    # -- headline cards ----------------------------------------------------
    clean = metrics.clean_export_rate or {}
    clean_pct = clean.get("clean_pct")
    target_class = (
        "target-hit"
        if clean_pct is not None and float(clean_pct) >= 60
        else "target-miss"
        if clean_pct is not None
        else ""
    )
    timing = metrics.time_to_first_export or {}
    cost = metrics.run_cost or {}
    parts.append(
        '<div class="cards">'
        f'<div class="card"><div class="sub">Exported with zero regeneration</div>'
        f'<div class="big {target_class}">{_fmt(clean_pct, 1)}%</div>'
        f'<div class="note">target &ge; 60% · {clean.get("clean_runs", 0)} of '
        f"{clean.get('exported_runs', 0)} runs</div></div>"
        f'<div class="card"><div class="sub">Time to first export (median)</div>'
        f'<div class="big">{_duration(timing.get("median_seconds"))}</div>'
        f'<div class="note">p90 {_duration(timing.get("p90_seconds"))} · '
        f"{timing.get('accounts', 0)} accounts</div></div>"
        f'<div class="card"><div class="sub">Run duration (median)</div>'
        f'<div class="big">{_duration((cost.get("median_duration_ms") or 0) / 1000)}</div>'
        f'<div class="note">p90 '
        f"{_duration((cost.get('p90_duration_ms') or 0) / 1000)} · "
        f"{cost.get('runs', 0)} runs</div></div>"
        f'<div class="card"><div class="sub">Inference cost per run (median)</div>'
        f'<div class="big">${_fmt(cost.get("median_cost"), 4)}</div>'
        f'<div class="note">${_fmt(cost.get("total_cost"), 4)} total</div></div>'
        "</div>"
    )

    # -- funnel ------------------------------------------------------------
    parts.append(
        "<h2>Funnel</h2><table><tr><th>Step</th><th class='n'>Accounts</th>"
        "<th class='n'>Of previous</th><th class='n'>Of start</th>"
        "<th style='width:32%'></th></tr>"
    )
    top = max((step.accounts for step in metrics.funnel), default=0)
    for step in metrics.funnel:
        drop = f'<span class="drop">−{step.dropped}</span>' if step.dropped else ""
        parts.append(
            f"<tr><td>{escape(STEP_LABELS.get(step.name, step.name))}</td>"
            f"<td class='n'>{step.accounts}</td>"
            f"<td class='n'>{_fmt(step.from_previous_pct, 1)}% {drop}</td>"
            f"<td class='n'>{_fmt(step.from_start_pct, 1)}%</td>"
            f"<td>{_bar(step.accounts, top)}</td></tr>"
        )
    parts.append("</table>")

    # -- the review gate ---------------------------------------------------
    review = metrics.review or {}
    parts.append("<h2>The review gate</h2>")
    parts.append(
        '<p class="note">Zero edits means two opposite things. These buckets '
        "separate them: a confirmation with no edits counts as inspected only "
        "if the user actually viewed most of the model and spent time "
        "proportional to its size.</p>"
    )
    parts.append(
        "<table><tr><th>Outcome</th><th class='n'>Confirmations</th>"
        "<th class='n'>Share</th><th class='n'>Median active</th>"
        "<th class='n'>Median coverage</th><th>What it means</th></tr>"
    )
    total = review.get("total", 0)
    for bucket in review.get("buckets", []):
        verdict = bucket["verdict"]
        parts.append(
            f"<tr><td style='color:{VERDICT_COLOURS[verdict]};font-weight:600'>"
            f"{escape(VERDICT_LABELS[verdict])}</td>"
            f"<td class='n'>{bucket['confirmations']}</td>"
            f"<td class='n'>{_fmt(bucket['share_pct'], 1)}%</td>"
            f"<td class='n'>{_duration(bucket['median_active_seconds'])}</td>"
            f"<td class='n'>{_fmt((bucket['median_coverage'] or 0) * 100, 0)}%</td>"
            f"<td class='note'>{escape(bucket['meaning'])}</td></tr>"
        )
    parts.append(f"</table><p class='note'>{total} confirmations in the window.</p>")

    # -- edit distribution -------------------------------------------------
    parts.append(
        "<h2>Edits before confirming</h2><table>"
        "<tr><th>Edits</th><th class='n'>Confirmations</th>"
        "<th style='width:45%'></th></tr>"
    )
    peak = max((row["confirmations"] for row in metrics.edit_distribution), default=0)
    for row in metrics.edit_distribution:
        label = "10+" if row["edits"] >= 10 else str(row["edits"])
        colour = VERDICT_COLOURS["rubber_stamped"] if row["edits"] == 0 else "#2f6f4e"
        parts.append(
            f"<tr><td>{label}</td><td class='n'>{row['confirmations']}</td>"
            f"<td>{_bar(row['confirmations'], peak, colour)}</td></tr>"
        )
    parts.append("</table>")

    # -- diagram failures --------------------------------------------------
    parts.append(
        "<h2>Diagram outcomes by type</h2><table>"
        "<tr><th>Diagram</th><th class='n'>Attempts</th>"
        "<th class='n'>Failed</th><th class='n'>Skipped</th>"
        "<th class='n'>Failure rate</th></tr>"
    )
    for row in metrics.diagram_failures:
        parts.append(
            f"<tr><td>{escape(row['diagram_type'])}</td>"
            f"<td class='n'>{row['attempts']}</td>"
            f"<td class='n'>{row['failed']}</td>"
            f"<td class='n'>{row['skipped']}</td>"
            f"<td class='n'>{_fmt(row['failure_pct'], 1)}%</td></tr>"
        )
    if not metrics.diagram_failures:
        parts.append("<tr><td colspan='5' class='note'>no runs in this window</td></tr>")
    parts.append("</table>")

    return "\n".join(parts)
