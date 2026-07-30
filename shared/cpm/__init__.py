"""Canonical Project Model.

This package is installed into BOTH the api and worker images. It is the only
place the CPM is defined. Do not copy any part of it into either service —
two definitions can drift, and the first symptom of drift is an entity name
differing between what the API stored and what the worker rendered, which is
exactly the FR-10 failure the consistency validator exists to prevent.
"""

from cpm.ids import MAX_SLUG_LENGTH, SLUG_PATTERN, Slug, is_slug, slugify
from cpm.integrity import IntegrityCode, IntegrityIssue, check_integrity
from cpm.schema import (
    CPM,
    Actor,
    Attribute,
    Component,
    CPMDraft,
    Entity,
    Flow,
    FlowStep,
    Meta,
    Method,
    Node,
    Relationship,
    RelationshipType,
    Requirement,
    RequirementType,
    State,
    Transition,
    UseCase,
)
from cpm.version import CPM_SCHEMA_VERSION

__all__ = [
    "CPM",
    "CPMDraft",
    "CPM_SCHEMA_VERSION",
    "MAX_SLUG_LENGTH",
    "SLUG_PATTERN",
    "Actor",
    "Attribute",
    "Component",
    "Entity",
    "Flow",
    "FlowStep",
    "IntegrityCode",
    "IntegrityIssue",
    "Meta",
    "Method",
    "Node",
    "Relationship",
    "RelationshipType",
    "Requirement",
    "RequirementType",
    "Slug",
    "State",
    "Transition",
    "UseCase",
    "check_integrity",
    "is_slug",
    "slugify",
]
