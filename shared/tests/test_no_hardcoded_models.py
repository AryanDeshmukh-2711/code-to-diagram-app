"""Guardrail: no model identifier may appear outside the LLM Gateway.

Constraint C-2 says the gateway is the only module that knows a model name.
That is trivially true on the day it is written and quietly false three months
later, when somebody hardcodes a model into a worker handler to debug something
and never takes it out. This test is the thing that notices.

Two deliberate design points:

* The scanner is exercised against a planted violation (see the meta-tests), so
  a passing run means "nothing found", never "the scanner silently matched
  nothing".
* The scan root is asserted to actually contain the repo. A guardrail pointed
  at an empty directory passes every time and protects nothing.

This file is itself exempt, because it necessarily contains the patterns it
searches for.
"""

import os
import re
from pathlib import Path

import pytest

REPO_ROOT = Path(os.environ.get("ASA_REPO_ROOT", Path(__file__).resolve().parents[2]))

GATEWAY_PACKAGE = "shared/llm"
"""The one place a model identifier is allowed to appear."""

SCANNED_SUFFIXES = {
    ".py",
    ".ts",
    ".tsx",
    ".js",
    ".jsx",
    ".mjs",
    ".cjs",
    ".json",
    ".yml",
    ".yaml",
    ".toml",
    ".ini",
    ".cfg",
    ".sh",
}
SCANNED_FILENAMES = {"Dockerfile", "Makefile"}

SKIPPED_DIRS = {
    ".git",
    ".venv",
    "venv",
    "node_modules",
    ".next",
    "out",
    "__pycache__",
    ".pytest_cache",
    ".ruff_cache",
    ".mypy_cache",
    "dist",
    "build",
}

SKIPPED_FILES = {
    "web/package-lock.json",  # generated dependency graph
    "web/src/lib/cpm.generated.ts",  # generated from the CPM schema
    "schemas/cpm.schema.json",  # generated from the Pydantic models
    "shared/tests/test_no_hardcoded_models.py",  # this file
}

MODEL_PATTERNS = {
    "anthropic": r"claude-(?:opus|sonnet|haiku|fable|mythos|instant|\d)",
    "openai": r"\bgpt-?\d|\bo[1-4]-(?:mini|preview)\b|text-embedding-\d",
    "google": r"\bgemini-[\d.]",
    "meta": r"\b(?:code)?llama-?\d",
    "mistral": r"\bmi[sx]tral[-:\d]",
    "qwen": r"\bqwen-?\d",
    "gemma": r"\bgemma-?\d",
    "deepseek": r"\bdeepseek[-:\w]*\d",
    "microsoft": r"\bphi-[34]\b",
    "xai": r"\bgrok-\d",
    "cohere": r"\bcommand-r\b",
}

SDK_PATTERNS = {
    "anthropic sdk": r"^\s*(?:import|from)\s+anthropic\b",
    "openai sdk": r"^\s*(?:import|from)\s+openai\b|from\s+[\"']openai[\"']",
    "google genai sdk": r"google\.generativeai|from\s+google\s+import\s+genai",
    "ollama sdk": r"^\s*(?:import|from)\s+ollama\b",
    "groq sdk": r"^\s*(?:import|from)\s+groq\b",
}


def _scannable_files(root: Path) -> list[Path]:
    # os.walk with in-place pruning rather than rglob: node_modules alone is
    # tens of thousands of files, and walking it only to discard it makes the
    # guardrail slow enough that someone will be tempted to skip it.
    found: list[Path] = []
    for directory, subdirectories, filenames in os.walk(root):
        subdirectories[:] = [d for d in subdirectories if d not in SKIPPED_DIRS]
        for filename in filenames:
            path = Path(directory) / filename
            if path.suffix in SCANNED_SUFFIXES or path.name in SCANNED_FILENAMES:
                found.append(path)
    return found


def find_violations(
    root: Path,
    patterns: dict[str, str],
    *,
    exempt_package: str | None = GATEWAY_PACKAGE,
    skipped_files: set[str] = SKIPPED_FILES,
) -> list[tuple[str, int, str, str]]:
    """Every (relative_path, line_number, vendor, line) match outside the gateway."""
    compiled = {
        name: re.compile(pattern, re.IGNORECASE | re.MULTILINE)
        for name, pattern in patterns.items()
    }
    violations: list[tuple[str, int, str, str]] = []

    for path in _scannable_files(root):
        relative = path.relative_to(root).as_posix()
        if exempt_package and relative.startswith(f"{exempt_package}/"):
            continue
        if relative in skipped_files:
            continue
        try:
            text = path.read_text(encoding="utf-8")
        except (UnicodeDecodeError, OSError):
            continue
        for number, line in enumerate(text.splitlines(), start=1):
            for vendor, regex in compiled.items():
                if regex.search(line):
                    violations.append((relative, number, vendor, line.strip()[:120]))
    return violations


def _render(violations: list[tuple[str, int, str, str]]) -> str:
    return "\n".join(
        f"  {path}:{line} [{vendor}] {text}" for path, line, vendor, text in violations
    )


# --------------------------------------------------------------------------
# The guardrail itself
# --------------------------------------------------------------------------


def test_no_model_identifier_appears_outside_the_gateway() -> None:
    violations = find_violations(REPO_ROOT, MODEL_PATTERNS)
    assert not violations, (
        "Model identifiers must appear only in "
        f"{GATEWAY_PACKAGE}/ (constraint C-2). Found:\n{_render(violations)}"
    )


def test_no_llm_sdk_is_imported_outside_the_gateway() -> None:
    violations = find_violations(REPO_ROOT, SDK_PATTERNS)
    assert not violations, (
        "LLM provider SDKs may only be imported inside "
        f"{GATEWAY_PACKAGE}/ (constraint C-2). Found:\n{_render(violations)}"
    )


def test_the_gateway_itself_does_declare_models() -> None:
    # The mirror image: if the gateway contains no model identifier at all,
    # either the scan is broken or the config is empty — and the two tests
    # above would pass for the wrong reason.
    inside = find_violations(REPO_ROOT, MODEL_PATTERNS, exempt_package=None, skipped_files=set())
    gateway_hits = [v for v in inside if v[0].startswith(f"{GATEWAY_PACKAGE}/")]
    assert gateway_hits, f"expected model identifiers inside {GATEWAY_PACKAGE}/, found none"


# --------------------------------------------------------------------------
# Anti-vacuous checks: prove the scan sees the repo, and that it can fail
# --------------------------------------------------------------------------


def test_the_scan_root_really_is_the_repository() -> None:
    # A guardrail pointed at an empty directory passes forever.
    assert REPO_ROOT.is_dir(), f"scan root {REPO_ROOT} does not exist"
    for expected in ("api", "web", "worker", "shared"):
        assert (REPO_ROOT / expected).is_dir(), (
            f"{expected}/ not found under {REPO_ROOT} — the scan is not covering the repo. "
            "In the api container this needs the repo-root bind mount (ASA_REPO_ROOT)."
        )


def test_the_scan_covers_a_substantial_number_of_files() -> None:
    assert len(_scannable_files(REPO_ROOT)) > 30


@pytest.mark.parametrize(
    ("filename", "content"),
    [
        ("handler.py", 'MODEL = "claude-opus-5"\n'),
        ("client.ts", 'const model = "gpt-4o";\n'),
        ("worker.py", 'model = "llama-3.1-70b"\n'),
        ("cfg.yaml", "model: qwen2.5:7b\n"),
        ("svc.py", 'MODEL = "gemini-2.0-flash"\n'),
        ("Dockerfile", 'ENV MODEL="mistral-7b"\n'),
    ],
)
def test_the_scanner_detects_a_planted_model_identifier(
    tmp_path: Path, filename: str, content: str
) -> None:
    # Without this, "no violations found" could mean the regexes match nothing
    # at all and the guardrail is decorative.
    (tmp_path / filename).write_text(content, encoding="utf-8")
    assert find_violations(tmp_path, MODEL_PATTERNS, exempt_package=None)


@pytest.mark.parametrize(
    ("filename", "content"),
    [
        ("a.py", "import anthropic\n"),
        ("b.py", "from openai import OpenAI\n"),
        ("c.py", "import ollama\n"),
        ("d.ts", 'import OpenAI from "openai";\n'),
    ],
)
def test_the_scanner_detects_a_planted_sdk_import(
    tmp_path: Path, filename: str, content: str
) -> None:
    (tmp_path / filename).write_text(content, encoding="utf-8")
    assert find_violations(tmp_path, SDK_PATTERNS, exempt_package=None)


def test_the_scanner_exempts_the_gateway_package(tmp_path: Path) -> None:
    gateway = tmp_path / GATEWAY_PACKAGE
    gateway.mkdir(parents=True)
    (gateway / "config.py").write_text('MODEL = "claude-opus-5"\n', encoding="utf-8")
    assert find_violations(tmp_path, MODEL_PATTERNS) == []


def test_the_scanner_ignores_generated_and_vendored_trees(tmp_path: Path) -> None:
    vendored = tmp_path / "node_modules" / "pkg"
    vendored.mkdir(parents=True)
    (vendored / "index.js").write_text('const m = "gpt-4";\n', encoding="utf-8")
    assert find_violations(tmp_path, MODEL_PATTERNS) == []
