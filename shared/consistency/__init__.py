"""FR-10 consistency validation.

Every entity, actor and relationship name in every generated artefact must be
byte-identical to its name in the CPM. There is no configuration here and no
severity level: a mismatch fails the run.
"""

from consistency.names import (
    ExtractedName,
    UnsupportedSourceLanguage,
    extract_mermaid,
    extract_names,
    extract_plantuml,
)
from consistency.validator import (
    ConsistencyReport,
    ConsistencyViolation,
    NameViolation,
    cpm_display_names,
    validate_consistency,
)

__all__ = [
    "ConsistencyReport",
    "ConsistencyViolation",
    "ExtractedName",
    "NameViolation",
    "UnsupportedSourceLanguage",
    "cpm_display_names",
    "extract_mermaid",
    "extract_names",
    "extract_plantuml",
    "validate_consistency",
]
