"""C-3, extended: the chat-edit family's no-bypass guard, generalized.

`test_confirm_is_not_chat_parseable.py` pinned two specific files against two
specific names (`confirm_draft`, `CPMVersionRow`). That was correct the day it
was written and silently incomplete the day a new module joined the chat-edit
family — a fixed file list does not grow itself, and a scanner pointed at a
list one module short of the truth passes for the wrong reason.

This module is a directory walk instead: every `.py` file the chat-edit
family currently contains, checked against every name `apply_edit_op`'s own
dispatch table calls plus the confirm path FR-6/FR-7 says chat text may never
reach. A file dropped into `shared/chat/` next month is covered the next run,
the same way `test_no_hardcoded_models.py`'s whole-repo walk already covers a
new file anywhere else for C-2.

Both CHAT-1 (`acceptance/chat1.py`) and the pytest guard
(`shared/tests/test_chat_pipeline_no_bypass.py`) call the functions here
rather than each keeping their own copy — one scanner, not two that could
check different things (the same reason `apply_edit_op` itself is the CPM's
one mutation dispatcher, not two implementations of what an edit means).
"""

import ast
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]

CHAT_FAMILY_FILES = (
    REPO_ROOT / "api" / "app" / "routers" / "chat.py",
    REPO_ROOT / "shared" / "generation" / "chat_edit.py",
)
"""Single files: the HTTP entry point for a chat message, and the worker
handler that actually parses and applies one."""

CHAT_FAMILY_DIRS = (REPO_ROOT / "shared" / "chat",)
"""Whole packages, walked rather than named file-by-file: intent.py,
service.py, result.py today, whatever else tomorrow."""

# Every individual operation apply_edit_op's own dispatch table calls
# (shared/review/edit_request.py) — importing one of these directly anywhere
# in the chat family is exactly the "second implementation of what an edit
# means" C-3 forbids, whether or not it is ever called.
FORBIDDEN_MUTATION_NAMES = {
    "rename_entity",
    "rename_actor",
    "rename_use_case",
    "delete_entity",
    "delete_actor",
    "delete_relationship",
    "delete_use_case",
    "delete_attribute",
    "add_entity",
    "add_actor",
    "add_attribute",
    "add_relationship",
    "relink_relationship",
    "set_use_case_actors",
    # FR-6/FR-7: confirming a model is a button, never a parsed op — folded
    # in here rather than kept a second, narrower scanner.
    "confirm_draft",
}
FORBIDDEN_TYPE_NAMES = {"CPMVersionRow"}
"""Confirming writes this row. Nothing chat-parsed may import the type that
would let it."""

ALLOWED_NAME = "apply_edit_op"
"""The one dispatcher C-3 permits. Its own module (edit_request.py) is not
part of the family being scanned — it is the destination, not a caller."""


def chat_family_modules() -> list[Path]:
    """Every `.py` file the chat-edit family currently has."""
    modules = [path for path in CHAT_FAMILY_FILES if path.is_file()]
    for directory in CHAT_FAMILY_DIRS:
        modules.extend(
            sorted(p for p in directory.glob("*.py") if p.name != "__init__.py")
        )
    return modules


def _imported_names(tree: ast.AST) -> set[str]:
    names: set[str] = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.ImportFrom):
            names.update(alias.asname or alias.name for alias in node.names)
    return names


def find_mutation_bypass_violations(
    modules: list[Path] | None = None,
) -> list[tuple[Path, set[str]]]:
    """`(path, offending names)` for every module that imports a CPM-mutation
    primitive directly, or the confirm path, instead of going through
    `apply_edit_op`."""
    violations = []
    for path in modules if modules is not None else chat_family_modules():
        imported = _imported_names(ast.parse(path.read_text(encoding="utf-8")))
        offending = imported & (FORBIDDEN_MUTATION_NAMES | FORBIDDEN_TYPE_NAMES)
        if offending:
            violations.append((path, offending))
    return violations


def family_calls_apply_edit_op(modules: list[Path] | None = None) -> bool:
    """Anti-vacuous: if nothing in the family ever imports `apply_edit_op`,
    there is no edit path here for the checks above to have caught a bypass
    of, and a clean scan would mean nothing."""
    for path in modules if modules is not None else chat_family_modules():
        if ALLOWED_NAME in _imported_names(ast.parse(path.read_text(encoding="utf-8"))):
            return True
    return False
