"""CHAT-1 — the acceptance test for the chat-driven frontend (P-M6).

AT-1 (SRS §10.1) proves the document pipeline. CHAT-1 proves the surface most
people will actually use to reach it: register, describe a project in plain
text, watch extraction happen, ask for a change in chat and see it land
correctly, confirm the model through the one button that may ever confirm it,
generate, and export — the signed link at the end downloaded and checked, not
just assumed to exist.

Run it with:

    make chat1

Same reporting discipline as AT-1 (acceptance/report.py): every promise is
checked independently and named; a failure says what was expected, what was
found, and — where known — the fix. No bare stack trace, and one broken
promise does not stop the rest from being checked.

Every step below goes through the real HTTP surface and the real worker,
exactly as the browser does — never a service called in-process to skip
what the product actually runs on the way. Chat-driven extraction and the
chat edit both need a model; when none is reachable this reports one
blocked check up front and stops, rather than guessing at what a real run
would have found.
"""

import argparse
import asyncio
import os
import sys
import time
from pathlib import Path

import httpx

from guards import (
    chat_family_modules,
    family_calls_apply_edit_op,
    find_mutation_bypass_violations,
)
from report import Report

FIXTURES = Path(__file__).resolve().parent / "fixtures"
DESCRIPTION = FIXTURES / "chat1_description.txt"

ACCOUNT_TIER = "pro"
"""Same reasoning as AT-1's own choice: a plan entitled to everything this
test exercises, so a failure reads as a pipeline bug, not a billing one —
quota refusals are P-M6-11's own acceptance surface, not this one's."""

BUDGET_SECONDS = 120.0
BASE = os.getenv("CHAT1_API", os.getenv("AT1_API", "http://localhost:8000"))
POLL_INTERVAL = 0.3

RENAME_TARGET = "Assignment"
"""What the one chat-driven edit renames the extracted entity to. Fixed and
distinctive on purpose: a match against this exact string later is a match
against something the edit produced, not something already in the draft."""

CONFIRM_ATTEMPT_MESSAGE = "Please confirm this model now and lock it in."
"""Reads exactly like the thing a button does. If parsing ever produced a
confirm-shaped outcome for text like this, that would be C-3/FR-6/FR-7
breaking, not working as designed — see the check this drives."""


async def _model_reachable() -> bool:
    base = os.getenv("LLM_BASE_URL")
    if not base:
        return False
    try:
        async with httpx.AsyncClient(timeout=3) as client:
            await client.get(f"{base.rstrip('/')}/api/tags")
        return True
    except Exception:
        return False


async def _entitled_session(client: httpx.AsyncClient) -> tuple[str, dict[str, str]]:
    """Register, sign in, and return the account id with its auth header —
    through the real endpoints, exactly as a new user reaches them."""
    registered = await client.post(f"{BASE}/auth/register", json={"tier": ACCOUNT_TIER})
    registered.raise_for_status()
    account = registered.json()

    session = await client.post(
        f"{BASE}/auth/token",
        json={"accountId": account["accountId"], "apiKey": account["apiKey"]},
    )
    session.raise_for_status()
    return account["accountId"], {"Authorization": f"Bearer {session.json()['token']}"}


async def _poll(
    client: httpx.AsyncClient, url: str, auth: dict, *, deadline: float
) -> dict:
    """GET url until `status` reaches a terminal value or the deadline
    passes — the same shape every progress card in the chat UI polls."""
    while time.perf_counter() < deadline:
        response = await client.get(url, headers=auth)
        response.raise_for_status()
        body = response.json()
        if body.get("status") in ("succeeded", "failed"):
            return body
        await asyncio.sleep(POLL_INTERVAL)
    raise TimeoutError(f"{url} did not reach a terminal status inside the budget")


async def _extract(
    client: httpx.AsyncClient, project_id: str, text: str, auth: dict, deadline: float
) -> dict:
    """POST .../extract, over HTTP, queued for the real worker — never the
    extraction service called in-process."""
    started = await client.post(
        f"{BASE}/projects/{project_id}/extract",
        data={"text": text, "projectName": "CHAT-1 project"},
        headers=auth,
    )
    started.raise_for_status()
    extraction_id = started.json()["extractionId"]
    return await _poll(
        client,
        f"{BASE}/projects/{project_id}/extractions/{extraction_id}",
        auth,
        deadline=deadline,
    )


async def _chat_edit(
    client: httpx.AsyncClient,
    project_id: str,
    message: str,
    auth: dict,
    deadline: float,
) -> dict:
    """POST .../chat, over HTTP, queued for the real worker — the exact
    surface the composer calls."""
    started = await client.post(
        f"{BASE}/projects/{project_id}/chat",
        json={"message": message},
        headers=auth,
    )
    started.raise_for_status()
    edit_id = started.json()["editId"]
    return await _poll(
        client,
        f"{BASE}/projects/{project_id}/chat/{edit_id}",
        auth,
        deadline=deadline,
    )


async def _review(client: httpx.AsyncClient, project_id: str, auth: dict) -> dict:
    response = await client.get(f"{BASE}/projects/{project_id}/review", headers=auth)
    response.raise_for_status()
    return response.json()


# ---------------------------------------------------------------------------
# The assertions
# ---------------------------------------------------------------------------


async def run_chat1() -> Report:
    report = Report(
        label="CHAT-1",
        subtitle="Chat-driven frontend — end-to-end acceptance (P-M6)",
        budget_seconds=BUDGET_SECONDS,
        success_line="The chat surface works end to end.",
    )
    started = time.perf_counter()

    text = DESCRIPTION.read_text(encoding="utf-8")
    report.notes.append(f"input       {len(text.split())}-word description")
    report.notes.append(
        "pipeline    register -> extract -> chat edit -> confirm -> generate -> "
        "export, all over real HTTP through the real worker"
    )

    # -- structural guards first: fast, deterministic, no network needed ----
    violations = find_mutation_bypass_violations()
    modules = chat_family_modules()
    report.add(
        "No chat-family module bypasses apply_edit_op",
        not violations,
        (
            f"{len(modules)} modules scanned, {len(violations)} bypass"
            f"{'es' if len(violations) != 1 else ''}"
        ),
        "zero bypasses (C-3, FR-6/FR-7)",
        "\n".join(
            f"{path.name} imports {', '.join(sorted(names))} directly"
            for path, names in violations
        ),
    )
    report.add(
        "The chat family actually reaches apply_edit_op",
        family_calls_apply_edit_op(),
        "yes" if family_calls_apply_edit_op() else "no",
        "apply_edit_op imported somewhere in the family",
        "if this fails, the check above is not guarding an edit path at all",
    )

    if not await _model_reachable():
        report.blocked(
            "Extraction and chat-edit parsing",
            "no model server reachable (LLM_BASE_URL)",
            "start a model server (e.g. ollama) and re-run; unlike AT-1, CHAT-1 "
            "drives the real worker over HTTP and has no in-process replay path",
        )
        report.seconds = time.perf_counter() - started
        return report

    project_id = f"chat1_{int(time.time())}"
    deadline = time.perf_counter() + BUDGET_SECONDS

    async with httpx.AsyncClient(timeout=BUDGET_SECONDS) as client:
        # -- register + sign in ----------------------------------------------
        account, auth = await _entitled_session(client)
        report.notes.append(
            f"account     {account} on the {ACCOUNT_TIER} plan, signed in"
        )

        # -- extraction, narrated ---------------------------------------------
        extraction = await _extract(client, project_id, text, auth, deadline)
        report.add(
            "Extraction succeeds and is narratable",
            extraction["status"] == "succeeded"
            and extraction["outcome"] == "extracted",
            f"status={extraction['status']!r} outcome={extraction.get('outcome')!r}",
            "status='succeeded' outcome='extracted'",
            extraction.get("error") or extraction.get("reason") or "",
        )
        if extraction["status"] != "succeeded" or extraction["outcome"] != "extracted":
            report.seconds = time.perf_counter() - started
            return report

        before = await _review(client, project_id, auth)
        entities_before = before["draft"].get("entities", [])
        report.add(
            "The extracted draft has an entity to edit",
            len(entities_before) >= 1,
            f"{len(entities_before)} entities",
            ">= 1",
            "the description did not support even one entity",
        )
        if not entities_before:
            report.seconds = time.perf_counter() - started
            return report
        old_name = entities_before[0]["name"]

        # -- a chat-driven edit, applied and verified correct ------------------
        edit = await _chat_edit(
            client, project_id, f"rename {old_name} to {RENAME_TARGET}", auth, deadline
        )
        report.add(
            "Chat-driven edit applies",
            edit["status"] == "succeeded" and edit["outcome"] == "applied",
            f"status={edit['status']!r} outcome={edit.get('outcome')!r}",
            "status='succeeded' outcome='applied'",
            edit.get("error")
            or edit.get("reason")
            or edit.get("clarifyQuestion")
            or "",
        )

        after = await _review(client, project_id, auth)
        names_after = {e["name"] for e in after["draft"].get("entities", [])}
        report.add(
            "The applied edit actually changed the model",
            RENAME_TARGET in names_after and old_name not in names_after,
            f"entities now: {sorted(names_after)}",
            f"{old_name!r} replaced by {RENAME_TARGET!r}",
            "the chat report claimed 'applied' but the draft was not the report",
        )

        # -- confirming stays a button, never a parsed intent (C-3, FR-6/FR-7) -
        confirm_attempt = await _chat_edit(
            client, project_id, CONFIRM_ATTEMPT_MESSAGE, auth, deadline
        )
        untouched = await _review(client, project_id, auth)
        draft_unchanged = untouched["draft"] == after["draft"]
        report.add(
            "A chat message that reads like a confirm request confirms nothing",
            confirm_attempt.get("outcome") != "applied" and draft_unchanged,
            f"outcome={confirm_attempt.get('outcome')!r}, "
            f"draft unchanged={draft_unchanged}",
            "no confirm-shaped outcome exists to produce, and the draft is untouched",
            "the parser vocabulary (shared/chat/intent.py) has no confirm op — "
            "see test_confirm_is_not_chat_parseable.py for the structural pin",
        )

        # -- explicit confirm, via the endpoint the button calls ---------------
        confirmed = await client.post(
            f"{BASE}/projects/{project_id}/review/confirm", json={}, headers=auth
        )
        confirmed.raise_for_status()
        version = confirmed.json()
        report.add(
            "Confirm succeeds through the real endpoint",
            bool(version.get("versionId")) and version.get("version") == 1,
            f"versionId={version.get('versionId')!r} version={version.get('version')}",
            "a real versionId, version 1",
            "",
        )
        version_id = version["versionId"]

        # -- generation, narrated honestly on partial failure -------------------
        run_started = await client.post(
            f"{BASE}/runs",
            json={"projectId": project_id, "cpmVersionId": version_id, "format": "svg"},
            headers=auth,
        )
        run_started.raise_for_status()
        run_id = run_started.json()["runId"]
        run = await _poll(client, f"{BASE}/runs/{run_id}", auth, deadline=deadline)

        artefacts = run.get("artefacts", [])
        succeeded = [a for a in artefacts if a["status"] == "succeeded"]
        skipped = [a for a in artefacts if a["status"] == "skipped"]
        failed = [a for a in artefacts if a["status"] == "failed"]
        report.add(
            "Generation finishes and reports every diagram honestly",
            run["status"] == "succeeded"
            and not failed
            and len(succeeded) + len(skipped) + len(failed) == len(artefacts)
            and len(artefacts) > 0,
            f"{len(succeeded)} succeeded, {len(skipped)} skipped, {len(failed)} failed "
            f"of {len(artefacts)} requested",
            "run succeeded, zero unexplained failures, skipped kept distinct "
            "from failed (FR-11)",
            "\n".join(f"{a['diagramType']}: {a['error']}" for a in failed),
        )

        # A PDF prefers vector, but svglib cannot always convert every SVG an
        # engine produces — the export step's own answer to that is a raster
        # fallback, not a crash (same reason AT-1 renders both svg_run and
        # png_run before it ever exports). Seeding that fallback here is
        # exactly that, not a workaround: gather_figures reads every
        # succeeded rendition across every run sharing this cpm version, so
        # a second run in a different format is how a PNG becomes available
        # to fall back to, the same way generating again in the chat UI
        # would.
        png_started = await client.post(
            f"{BASE}/runs",
            json={"projectId": project_id, "cpmVersionId": version_id, "format": "png"},
            headers=auth,
        )
        png_started.raise_for_status()
        await _poll(
            client,
            f"{BASE}/runs/{png_started.json()['runId']}",
            auth,
            deadline=deadline,
        )

        # -- export, and the signed download verified reachable and non-empty --
        export_started = await client.post(
            f"{BASE}/runs/{run_id}/export",
            json={"format": "pdf", "templateId": "ieee-830-plain", "fields": {}},
            headers=auth,
        )
        export_started.raise_for_status()
        export_id = export_started.json()["exportId"]
        export = await _poll(
            client, f"{BASE}/exports/{export_id}", auth, deadline=deadline
        )
        report.add(
            "Export succeeds and returns a signed link",
            export["status"] == "succeeded" and bool(export.get("url")),
            f"status={export['status']!r} "
            f"url={'present' if export.get('url') else 'MISSING'}",
            "status='succeeded', a url present",
            export.get("error") or "",
        )

        if export.get("url"):
            downloaded = await client.get(f"{BASE}{export['url']}")
            ok = downloaded.status_code == 200 and len(downloaded.content) > 0
            report.add(
                "The signed download is reachable and non-empty",
                ok,
                f"HTTP {downloaded.status_code}, {len(downloaded.content)} bytes",
                "HTTP 200, > 0 bytes",
                "the export row reported success but the download link did not serve "
                "it",
            )
        else:
            report.blocked(
                "The signed download is reachable and non-empty",
                "no url to download — see the export check above",
            )

    report.seconds = time.perf_counter() - started
    report.add(
        "Total wall time",
        report.seconds < BUDGET_SECONDS,
        f"{report.seconds:.1f}s",
        f"< {BUDGET_SECONDS:.0f}s",
        "the run exceeded its budget; check queue wait and model latency",
    )
    return report


def main() -> int:
    parser = argparse.ArgumentParser(description="Run acceptance test CHAT-1")
    parser.add_argument("--json", action="store_true", help="emit the report as JSON")
    args = parser.parse_args()

    try:
        report = asyncio.run(run_chat1())
    except Exception as exc:
        print(f"CHAT-1 could not run to completion: {type(exc).__name__}: {exc}")
        print(
            "this is a harness failure, not an assertion failure — "
            "the stack trace follows"
        )
        raise

    if args.json:
        import json

        print(
            json.dumps(
                {
                    "passed": report.passed,
                    "seconds": round(report.seconds, 2),
                    "checks": [
                        {
                            "number": c.number,
                            "name": c.name,
                            "ok": c.ok,
                            "found": c.found,
                            "expected": c.expected,
                        }
                        for c in report.checks
                    ],
                },
                indent=2,
            )
        )
    else:
        print(report.render())
    return 0 if report.passed else 1


if __name__ == "__main__":
    sys.exit(main())
