"""The reporting discipline every acceptance test in this project shares.

Every assertion is evaluated independently and reported by name. A failure
prints what was expected, what was found, and — where the cause is known —
what to do about it. It does not print a traceback, because a traceback tells
you where Python gave up, not which promise the product broke. One broken
promise also does not stop the others being checked: the pipeline runs as far
as it can and the report says how far that was.

AT-1 (SRS §10.1) and CHAT-1 (P-M6-12) both render through this module rather
than each keeping their own copy of it, for the same reason `apply_edit_op` is
the CPM's one mutation dispatcher: two implementations of "how a check is
reported" would drift the first time one of them was fixed and the other
forgotten.
"""

import os
import sys
from dataclasses import dataclass, field

GREEN, RED, GREY, BOLD, RESET = "\033[32m", "\033[31m", "\033[90m", "\033[1m", "\033[0m"
if not sys.stdout.isatty() or os.getenv("NO_COLOR"):
    GREEN = RED = GREY = BOLD = RESET = ""


@dataclass
class Check:
    number: int
    name: str
    ok: bool
    found: str
    expected: str
    remedy: str = ""

    def render(self) -> str:
        mark = f"{GREEN}PASS{RESET}" if self.ok else f"{RED}FAIL{RESET}"
        lines = [f"  {mark}  {self.number:>2}. {self.name:<44} {self.found}"]
        if not self.ok:
            lines.append(f"           {GREY}expected{RESET} {self.expected}")
            for line in self.remedy.splitlines():
                if line.strip():
                    lines.append(f"           {GREY}->{RESET} {line.strip()}")
        return "\n".join(lines)


@dataclass
class Report:
    label: str
    """The acceptance test's own short name — "AT-1", "CHAT-1" — printed as
    the report's headline and in every summary line, so a failure pasted into
    a channel names which promise family broke without extra context."""
    subtitle: str
    budget_seconds: float
    success_line: str
    """What "PASSED" means for this particular acceptance test — "V1 works."
    for AT-1, something specific to what CHAT-1 covers for CHAT-1. Never a
    generic "all good!"; the whole point of this harness is specificity."""
    checks: list[Check] = field(default_factory=list)
    notes: list[str] = field(default_factory=list)
    replayed: bool = False
    seconds: float = 0.0

    def add(
        self, name: str, ok: bool, found: str, expected: str, remedy: str = ""
    ) -> Check:
        check = Check(len(self.checks) + 1, name, ok, found, expected, remedy)
        self.checks.append(check)
        return check

    def blocked(self, name: str, reason: str, remedy: str = "") -> Check:
        return self.add(name, False, "not reached", reason, remedy)

    @property
    def failures(self) -> list[Check]:
        return [check for check in self.checks if not check.ok]

    @property
    def passed(self) -> bool:
        return not self.failures and not self.replayed

    def render(self) -> str:
        width = 78
        lines = [
            "=" * width,
            f"{BOLD}{self.label}{RESET}  {self.subtitle}",
            "=" * width,
        ]
        lines.extend(self.notes)
        lines.append("")
        lines.extend(check.render() for check in self.checks)
        lines.append("-" * width)

        passes = len(self.checks) - len(self.failures)
        summary = f"{passes} passed, {len(self.failures)} failed"
        budget = f"wall time {self.seconds:.1f}s of {self.budget_seconds:.0f}s budget"
        lines.append(f"{summary}  ·  {budget}")

        if self.failures:
            lines.append("")
            lines.append(f"{RED}{BOLD}{self.label} FAILED{RESET}. Broken promises:")
            for check in self.failures:
                lines.append(f"  {check.number:>2}. {check.name} — {check.found}")
        elif self.replayed:
            lines.append("")
            lines.append(
                f"{RED}{BOLD}NOT A FULL {self.label} PASS{RESET}: every assertion "
                f"holds, but a step was replayed"
            )
            lines.append(
                "  from a recording rather than performed by a model. Start a model"
            )
            lines.append(f"  server and re-run to claim {self.label}.")
        else:
            lines.append("")
            lines.append(
                f"{GREEN}{BOLD}{self.label} PASSED{RESET}. {self.success_line}"
            )
        return "\n".join(lines)
