"""FR-6/FR-7, pinned: confirming a model is a single, explicit, non-inferable
UI action, and P-M6-2's parser has no way to produce one.

This is not a runtime guard -- there is no "if op == confirm: reject" check
anywhere, because there is nowhere such a check would need to fire. The
vocabulary the parser is allowed to choose from (chat.intent.EditOp) simply
has no confirm-shaped entry, and neither the chat router nor the worker
module that executes a parsed edit ever imports the confirm path
(confirm_draft, CPMVersionRow) at all. These tests exist so that adding
"confirm" to that vocabulary later "for convenience" -- the exact harm this
step's Watch For names -- fails a test before it ever reaches a review.
"""

from pathlib import Path
from typing import get_args

REPO_ROOT = Path(__file__).resolve().parents[2]


def test_the_parsers_op_vocabulary_has_no_confirm_shaped_entry() -> None:
    from chat.intent import EditOp

    ops = get_args(EditOp)
    assert "confirm" not in ops
    assert not any("confirm" in op for op in ops), ops


def test_the_chat_edit_intent_schema_has_no_confirm_field() -> None:
    from chat.intent import ChatEditIntent

    assert "confirm" not in ChatEditIntent.model_fields


def test_the_chat_router_never_reaches_the_confirm_path() -> None:
    source = (REPO_ROOT / "api" / "app" / "routers" / "chat.py").read_text(encoding="utf-8")
    assert "confirm_draft" not in source
    assert "CPMVersionRow" not in source


def test_the_chat_edit_worker_module_never_reaches_the_confirm_path() -> None:
    source = (REPO_ROOT / "shared" / "generation" / "chat_edit.py").read_text(encoding="utf-8")
    assert "confirm_draft" not in source
    assert "CPMVersionRow" not in source


def test_apply_edit_op_the_chat_pipelines_only_mutation_path_cannot_confirm() -> None:
    """The dispatcher chat's ParsedEdit ultimately runs through (C-3) has no
    branch that reaches confirm_draft, regardless of what op string it is
    handed."""
    from review import EDIT_OPS

    assert "confirm" not in EDIT_OPS
    assert not any("confirm" in op for op in EDIT_OPS)
