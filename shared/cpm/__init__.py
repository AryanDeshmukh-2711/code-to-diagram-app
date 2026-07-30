"""Canonical Project Model.

This package is installed into BOTH the api and worker images. It is the only
place the CPM is defined. Do not copy any part of it into either service —
two definitions can drift, and the first symptom of drift is an entity name
differing between what the API stored and what the worker rendered, which is
exactly the FR-10 failure the consistency validator exists to prevent.
"""

from cpm.version import CPM_SCHEMA_VERSION

__all__ = ["CPM_SCHEMA_VERSION"]
