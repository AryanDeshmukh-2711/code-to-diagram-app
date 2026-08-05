"""C-2/C-3, extended (P-M6-12): the chat-edit family's structural guards now
cover every module the family currently has, not a fixed list that goes stale
the moment a new file joins it.

`test_confirm_is_not_chat_parseable.py` proved FR-6/FR-7 against two named
files. `acceptance/guards.py` generalizes that into a directory walk shared
with CHAT-1 (`acceptance/chat1.py`), so this file and that acceptance test can
never check different things — one scanner, two callers, the same reason
`apply_edit_op` is the CPM's one mutation dispatcher rather than two
implementations that could drift.

Two families of check:

* C-3 — a chat-family module reaching CPM mutation through anything but
  `apply_edit_op` (importing an individual operation like `rename_entity`
  directly), or the confirm path (`confirm_draft`, `CPMVersionRow`) FR-6/FR-7
  says chat text may never reach.
* C-2 — not re-implemented here; `test_no_hardcoded_models.py`'s repo-wide
  scan already covers a new chat-family file the moment it exists. What this
  file adds is proof of that claim: every chat-family file is actually inside
  that scan's file list, not merely assumed to be.
"""

import os
import sys
from pathlib import Path

import pytest

REPO_ROOT = Path(os.environ.get("ASA_REPO_ROOT", Path(__file__).resolve().parents[2]))
sys.path.insert(0, str(REPO_ROOT / "acceptance"))

from guards import (  # noqa: E402
    chat_family_modules,
    family_calls_apply_edit_op,
    find_mutation_bypass_violations,
)
from test_no_hardcoded_models import _scannable_files  # noqa: E402


def test_there_are_chat_family_modules_to_check() -> None:
    # A guardrail over an empty set passes forever.
    assert chat_family_modules()


@pytest.mark.parametrize(
    "path", chat_family_modules(), ids=lambda p: p.relative_to(REPO_ROOT).as_posix()
)
def test_a_chat_family_module_never_bypasses_apply_edit_op(path: Path) -> None:
    violations = find_mutation_bypass_violations([path])
    assert not violations, (
        f"{path.relative_to(REPO_ROOT)} imports "
        f"{', '.join(sorted(violations[0][1]))} directly — every edit must reach the "
        f"CPM through apply_edit_op, and confirming is a button, never a parsed op "
        f"(C-3, FR-6/FR-7)"
    )


def test_the_family_does_call_apply_edit_op_somewhere() -> None:
    assert family_calls_apply_edit_op(), (
        "expected apply_edit_op to be imported somewhere in the chat family — "
        "if it is not, the checks above are not guarding an edit path at all"
    )


def test_the_detector_would_catch_a_planted_bypass(tmp_path: Path) -> None:
    # Without this, a clean scan could mean "nothing found" or "the scanner
    # silently matched nothing" — indistinguishable without a planted case.
    planted = tmp_path / "sneaky.py"
    planted.write_text("from review.operations import rename_entity\n", encoding="utf-8")
    assert find_mutation_bypass_violations([planted])


def test_the_detector_would_catch_a_planted_confirm_bypass(tmp_path: Path) -> None:
    planted = tmp_path / "sneaky.py"
    planted.write_text(
        "from review import confirm_draft\nfrom store.models import CPMVersionRow\n",
        encoding="utf-8",
    )
    violations = find_mutation_bypass_violations([planted])
    assert violations
    assert violations[0][1] == {"confirm_draft", "CPMVersionRow"}


def test_the_gateway_scan_covers_every_chat_family_file() -> None:
    scanned = {path.resolve() for path in _scannable_files(REPO_ROOT)}
    missing = [
        path.relative_to(REPO_ROOT).as_posix()
        for path in chat_family_modules()
        if path.resolve() not in scanned
    ]
    assert not missing, (
        f"these chat-family files are invisible to the C-2 gateway scan, so a model "
        f"import inside them would never be caught: {missing}"
    )
