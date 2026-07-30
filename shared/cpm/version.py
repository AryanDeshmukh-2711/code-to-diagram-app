"""Schema version for persisted CPM payloads.

Bump whenever the CPM shape changes. Stored alongside every CPMVersion row so
an artefact set can always be traced to the exact schema that produced it.
"""

CPM_SCHEMA_VERSION = "0.1.0"
