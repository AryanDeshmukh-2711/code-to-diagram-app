"""Reference CPM fixtures.

The Library Management System model is the corpus for AT-1 (SRS §10.1), the seed
for local development, and the input for every downstream diagram-mapper test.
It is shipped as package data rather than built in Python so it can also be
POSTed to the API, loaded by the web app, and diffed as a plain file.
"""

import json
from pathlib import Path
from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    from cpm.schema import CPM

FIXTURES_DIR = Path(__file__).resolve().parent
LIBRARY_MANAGEMENT_SYSTEM_PATH = FIXTURES_DIR / "library_management_system.json"

__all__ = [
    "FIXTURES_DIR",
    "LIBRARY_MANAGEMENT_SYSTEM_PATH",
    "library_management_system_payload",
    "load_library_management_system",
]


def library_management_system_payload() -> dict[str, Any]:
    """The raw fixture payload.

    Re-read from disk on every call so a caller that mutates it to build a
    negative test case cannot corrupt the next caller's copy.
    """
    return json.loads(LIBRARY_MANAGEMENT_SYSTEM_PATH.read_text(encoding="utf-8"))


def load_library_management_system() -> "CPM":
    """The fixture as a fully validated CPM."""
    from cpm.schema import CPM

    return CPM.model_validate(library_management_system_payload())
