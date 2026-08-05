# Software Requirements Specification

**Product:** AI Software Architect (working name; earlier internal name — UML Studio)
**Author:** Aryan Vijay Deshmukh
**Version:** 1.0
**Date:** 30 July 2026
**Conforms to:** IEEE 830-1998 structure, updated for ISO/IEC/IEEE 29148:2018 terminology
**Scope of this document:** Release V1 only. V2/V3 features are listed as out of scope in §2.7.

> **Note (2026-08-05):** This document was written for the project's original
> commercial-SaaS phase. The project has since pivoted to an open-source,
> local-first, single-user tool — it runs against the operator's own machine
> and their own LLM, with no accounts and no billing. The account/quota/tier
> requirements (former FR-21/FR-22/NFR-S2/NFR-M4) have been removed to match,
> and FR-20 (watermarking) with it. Surrounding infrastructure-scaling
> assumptions elsewhere in this document (multi-tenant, horizontally
> scalable) describe that earlier phase and have not been rewritten.
> CLAUDE.md is the current source of truth for product direction.

---

## Table of Contents

1. Introduction
2. Overall Description
3. System Architecture
4. External Interface Requirements
5. Functional Requirements
6. Data Requirements
7. Non-Functional Requirements
8. Diagram Engine Matrix
9. Constraints, Assumptions and Dependencies
10. Verification and Acceptance
11. Appendices

---

## 1. Introduction

### 1.1 Purpose

This document specifies the requirements for **AI Software Architect V1**, a web application that converts a natural-language project description or a requirements PDF into a consistent set of UML/ER diagrams and a formatted Software Requirements Specification document, exported as a submission-ready PDF or DOCX file.

The intended audience is the development team, reviewers, and any future contributor implementing or testing the system.

### 1.2 Product Scope

V1 accepts textual input, derives a structured **Canonical Project Model (CPM)**, allows the user to review and correct that model, then deterministically renders all artefacts from it. The system does **not** analyse source code in V1.

### 1.3 Definitions, Acronyms and Abbreviations

| Term | Definition |
|---|---|
| **CPM** | Canonical Project Model — the single structured intermediate representation from which every artefact is rendered |
| **Artefact** | Any generated output: a diagram, a document section, or a complete document |
| **Diagram engine** | A renderer converting textual diagram source into an image (PlantUML, Mermaid, Graphviz) |
| **Template** | A document skin defining cover page, certificate page, index, headers, footers and typography |
| **Generation run** | One end-to-end execution producing a full artefact set for one project |
| **LLM** | Large Language Model |
| **AST** | Abstract Syntax Tree |
| **OCR** | Optical Character Recognition |

### 1.4 References

- IEEE 830-1998 — Recommended Practice for Software Requirements Specifications
- ISO/IEC/IEEE 29148:2018 — Requirements engineering
- OMG Unified Modeling Language Specification v2.5.1
- PlantUML language reference
- Mermaid.js documentation

### 1.5 Overview

Section 2 gives the general product context. Section 3 defines the architecture. Sections 4–7 give interface, functional, data and quality requirements. Section 8 fixes the diagram engine decisions. Section 9 records constraints. Section 10 defines acceptance.

---

## 2. Overall Description

### 2.1 Product Perspective

A new, self-contained web product. It integrates with third-party LLM providers and diagram rendering engines but is not a component of any larger system. It is not a plugin, IDE extension, or CI tool in V1.

### 2.2 Product Functions

1. Ingest a project description as text or PDF.
2. Extract a Canonical Project Model.
3. Allow user review and correction of the CPM.
4. Render a consistent diagram set from the CPM.
5. Assemble an SRS document embedding those diagrams.
6. Apply a document template.
7. Export in multiple formats.

### 2.3 User Classes and Characteristics

| Class | Technical level | Frequency | Primary need |
|---|---|---|---|
| Student | Low–medium | 2–4 times per semester | Format-compliant submittable document |
| Freelancer | Medium–high | Weekly | Fast professional-looking client deliverable |
| Educator/reviewer | Medium | Occasional | Readable, standards-conformant output |
| Administrator | High | Continuous | System health, quota and cost monitoring |

### 2.4 Operating Environment

- **Client:** modern evergreen browsers (Chrome, Edge, Firefox, Safari — current and previous major version), desktop and tablet. Mobile is view-only in V1.
- **Server:** Linux containers, horizontally scalable stateless application nodes.
- **External services:** at least one LLM provider API; object storage; managed PostgreSQL; Redis.

### 2.5 Design and Implementation Constraints

- **C-1** Diagrams shall be rendered from declarative source (PlantUML/Mermaid), never as LLM-generated raster images, so output is reproducible and editable.
- **C-2** The LLM shall be accessed through a provider abstraction layer. No model identifier shall appear outside that layer.
- **C-3** Every artefact shall be rendered from the CPM. No artefact shall be produced by an independent LLM call that bypasses the CPM, as this is what causes cross-diagram inconsistency.
- **C-4** All long-running generation shall execute in an asynchronous job queue, not in the HTTP request cycle.

### 2.6 Assumptions and Dependencies

- **A-1** If a hosted LLM provider is configured in place of the local default, its API shall remain available at commercially viable per-token pricing. The default (local Ollama) has no such dependency: inference is free and offline.
- **A-2** The user can describe their project in at least 50 words of natural language.
- **A-3** Target institutions' document templates are obtainable and finite in number.
- **D-1** Dependency on PlantUML (requires a JVM or a hosted rendering service).
- **D-2** Dependency on a headless browser or equivalent for PDF pagination.

### 2.7 Out of Scope for V1

Repository/ZIP ingestion, AST parsing, dependency graphs, folder-structure diagrams, BPMN, customer journey maps, cloud architecture diagrams, HLD/LLD/API documentation, AI chat, real-time collaboration, version comparison, architecture review, SSO, on-premise deployment, multi-language code analysis.

---

## 3. System Architecture

### 3.1 Logical Components

| Component | Responsibility |
|---|---|
| **Web Client** | Input capture, CPM review UI, generation progress, preview, export triggers |
| **API Gateway** | Authentication, request validation, rate limiting, quota enforcement |
| **Ingestion Service** | Text normalisation, PDF text extraction, OCR fallback, chunking |
| **Extraction Service** | LLM-driven derivation of the CPM; schema validation of the result |
| **CPM Store** | Persistence and versioning of the canonical model |
| **Diagram Service** | CPM → diagram source → rendered SVG/PNG; syntax validation and retry |
| **Document Service** | Section assembly, figure numbering, template application, PDF/DOCX rendering |
| **Job Queue / Workers** | Asynchronous execution of generation runs |
| **Object Storage** | Uploads and generated binary artefacts |
| **LLM Gateway** | Provider abstraction, routing, retry, usage observability, caching |

### 3.2 Processing Pipeline

```
Input (text | PDF)
   │
   ├─ Ingestion: extract, normalise, chunk
   │
   ├─ Extraction: LLM → CPM (JSON) → schema validation
   │
   ├─ ► USER REVIEW GATE ◄  (mandatory; user corrects CPM)
   │
   ├─ Diagram Service: CPM → PlantUML/Mermaid source → render → validate
   │
   ├─ Document Service: CPM + diagrams + template → assembled document
   │
   └─ Export: PDF | DOCX | PNG | SVG | diagram source
```

**Architectural rationale for the review gate:** LLM extraction is probabilistic; rendering is deterministic. Placing a human checkpoint between them converts an unreliable pipeline into a reliable one, and is the primary control for requirement NFR-Q1.

---

## 4. External Interface Requirements

### 4.1 User Interfaces

- **UI-1** Project creation screen with a text area and a file drop zone.
- **UI-2** CPM review screen presenting entities, attributes, relationships, actors and use cases as editable structured lists, with add/rename/delete/link operations.
- **UI-3** Generation screen showing per-artefact progress and per-artefact failure states.
- **UI-4** Result screen with diagram previews, per-diagram regenerate action, and export controls.
- **UI-5** All destructive actions (delete project, discard model) require confirmation.
- **UI-6** The system shall display a persistent notice that generated content requires review before submission or publication.

### 4.2 Software Interfaces

| Interface | Direction | Purpose | Failure behaviour |
|---|---|---|---|
| LLM provider API | Outbound | CPM extraction, document prose | Retry with backoff; fail the run with a diagnostic message after 3 attempts |
| PlantUML renderer | Outbound | UML rendering | Fall back to Mermaid where the type permits; otherwise mark that diagram failed and continue the run |
| Object storage | Bidirectional | Uploads, artefacts | Fail the affected operation only |
| PostgreSQL | Bidirectional | Projects, CPM, users, quotas | Fail request |
| Redis | Bidirectional | Queue, cache, rate limits | Degrade to synchronous where safe |

### 4.3 Communications Interfaces

- HTTPS/TLS 1.2+ for all client-server traffic.
- JSON over REST for the application API.
- Server-sent events or polling for generation progress.

---

## 5. Functional Requirements

Each requirement states inputs, processing and outputs. Priority: **P0** blocker, **P1** desirable.

### 5.1 Input and Ingestion

**FR-1 — Text input**
*Priority:* P0
*Input:* free text, 50–20,000 characters.
*Processing:* validate length, strip control characters, normalise whitespace.
*Output:* normalised text stored against a new project.
*Error:* input below 50 characters shall be rejected with guidance on what to include.

**FR-2 — PDF input**
*Priority:* P0
*Input:* PDF file ≤ 25 MB, ≤ 100 pages.
*Processing:* extract embedded text; if extractable text is below a defined threshold, apply OCR.
*Output:* normalised text.
*Error:* encrypted, corrupt or oversized files shall be rejected with a specific reason.

**FR-3 — Input sanitisation**
*Priority:* P0
The system shall treat all ingested content as untrusted data and shall not execute instructions contained within it.

### 5.2 Model Extraction

**FR-4 — CPM extraction**
*Priority:* P0
*Input:* normalised text.
*Processing:* LLM extraction into the CPM schema (§6.1), followed by strict schema validation and a de-duplication/normalisation pass on entity names.
*Output:* a valid CPM instance.
*Error:* on schema-validation failure, retry once with a corrective prompt, then fail with a diagnostic.

**FR-5 — Extraction completeness floor**
*Priority:* P0
For an input of ≥ 200 words describing a system, the CPM shall contain at least 3 entities and at least 2 relationships, or the run shall report insufficient input rather than fabricate content.

**FR-6 — CPM review and edit**
*Priority:* P0
The user shall be able to add, rename, delete and re-link every element of the CPM before generation. Generation shall not proceed until the user explicitly confirms the model.

**FR-7 — CPM versioning**
*Priority:* P1
Each confirmed CPM shall be stored as an immutable version, so a prior artefact set can be traced to the exact model that produced it.

### 5.3 Diagram Generation

**FR-8 — Supported diagram types**
*Priority:* P0
The system shall generate: Class, Use Case, Sequence, Activity, State, Component, Deployment, and Entity-Relationship diagrams.

**FR-9 — Deterministic rendering**
*Priority:* P0
Given an identical CPM and identical diagram options, the system shall produce identical diagram source. Diagram source generation shall be rule-based over the CPM wherever the mapping is deterministic; the LLM shall be used only where genuine interpretation is required (e.g. sequence-flow ordering).

**FR-10 — Cross-artefact consistency**
*Priority:* P0
Every entity, actor and relationship name appearing in any artefact shall be byte-identical to its name in the CPM. A post-generation validator shall assert this and fail the run on violation.

**FR-11 — Syntax validation**
*Priority:* P0
Generated diagram source shall be validated by the rendering engine before being presented. On failure, the system shall retry once, then mark that individual diagram as failed without aborting the run.

**FR-12 — Selective regeneration**
*Priority:* P1
The user shall be able to regenerate any single diagram without regenerating the set.

### 5.4 Document Generation

**FR-13 — SRS assembly**
*Priority:* P0
The system shall assemble a document following the IEEE 830 section structure, populated from the CPM, with generated diagrams embedded as sequentially numbered and captioned figures.

**FR-14 — Template application**
*Priority:* P1
The system shall apply a selected template controlling cover page, certificate page, index table, running headers and footers, fonts and margins. At least 3 templates shall ship built in.

**FR-15 — Custom template**
*Priority:* P1
The user shall be able to supply institution-specific values (institution name, department, course code, enrolment number, student name, academic year, logo) that populate the template.

**FR-16 — Figure and section numbering**
*Priority:* P0
Figure numbers, section numbers and the index table shall be generated automatically and shall remain internally consistent.

### 5.5 Export

**FR-17 — Document export**
*Priority:* P0 — PDF and DOCX.
**FR-18 — Image export**
*Priority:* P0 — PNG and SVG per diagram.
**FR-19 — Source export**
*Priority:* P1 — PlantUML and Mermaid source per diagram.

### 5.6 Project Management

**FR-23** Users shall be able to list, open, rename, duplicate and delete their projects. *(P1)*
**FR-24** Deleting a project shall remove its artefacts from object storage within 24 hours. *(P1)*

---

## 6. Data Requirements

### 6.1 Canonical Project Model schema (conceptual)

```
CPM
├── meta            { projectName, description, authors[], version, createdAt }
├── actors[]        { id, name, description, isPrimary }
├── entities[]      { id, name, description,
│                     attributes[] { name, type, isKey, isRequired },
│                     methods[]    { name, returns, params[] } }
├── relationships[] { id, from, to, type, cardinality, label }
│                     type ∈ {association, aggregation, composition,
│                             inheritance, dependency, realization}
├── useCases[]      { id, name, actors[], preconditions[],
│                     mainFlow[], alternateFlows[], postconditions[] }
├── flows[]         { id, name, participants[], steps[] { from, to, message, order } }
├── states[]        { id, entityRef, name, isInitial, isFinal,
│                     transitions[] { to, trigger, guard } }
├── components[]    { id, name, type, provides[], requires[] }
├── nodes[]         { id, name, type, deployedComponents[] }
└── requirements[]  { id, type: functional|nonFunctional, text, priority }
```

### 6.2 Persisted Entities

| Entity | Key fields | Notes |
|---|---|---|
| Project | id, name, inputType, createdAt | |
| CPMVersion | id, projectId, version, payload (JSONB), confirmedAt | Immutable |
| GenerationRun | id, projectId, cpmVersionId, status, startedAt, completedAt, cost | |
| Artefact | id, runId, type, format, storageKey, status | |
| Template | id, ownerId (nullable for built-ins), name, config | |

### 6.3 Retention

- Uploaded source files: retained while the project exists; deleted within 24 hours of project deletion.
- Generated artefacts: same lifecycle as their project.
- Input content shall not be used for model training by default.

---

## 7. Non-Functional Requirements

### 7.1 Performance

| ID | Requirement |
|---|---|
| NFR-P1 | CPM extraction shall complete within 30 s (p90) for inputs ≤ 3,000 words |
| NFR-P2 | A full 8-diagram generation run shall complete within 180 s (p90) |
| NFR-P3 | Individual diagram rendering shall complete within 10 s (p95) |
| NFR-P4 | PDF assembly shall complete within 30 s (p90) for documents ≤ 40 pages |
| NFR-P5 | Interactive UI actions shall respond within 200 ms (p95), excluding generation |

### 7.2 Quality of Output

| ID | Requirement |
|---|---|
| NFR-Q1 | ≥ 95% of generated diagrams shall be syntactically valid on first render |
| NFR-Q2 | 100% of entity names shall be consistent across artefacts within a run (hard assert, FR-10) |
| NFR-Q3 | ≥ 60% of generation runs shall be exported without any regeneration request |
| NFR-Q4 | Generated documents shall contain no unresolved placeholder tokens |

### 7.3 Reliability and Availability

| ID | Requirement |
|---|---|
| NFR-R1 | 99.5% monthly availability of the web application |
| NFR-R2 | A failure in a single artefact shall not abort the remaining artefacts in a run |
| NFR-R3 | Generation jobs shall be idempotent and safely retryable |
| NFR-R4 | Daily backup of PostgreSQL with ≤ 24 h RPO |

### 7.4 Security and Privacy

| ID | Requirement |
|---|---|
| NFR-S1 | TLS in transit; encryption at rest for uploads and artefacts |
| NFR-S3 | Uploaded content shall be treated as untrusted data and never as instructions to the model |
| NFR-S4 | Signed, expiring URLs for all artefact downloads |
| NFR-S5 | Rate limiting per user and per IP on all generation endpoints |
| NFR-S6 | Secrets shall be held in a managed secret store, never in source or client bundles |

### 7.5 Scalability

| ID | Requirement |
|---|---|
| NFR-SC1 | Application nodes shall be stateless and horizontally scalable |
| NFR-SC2 | Generation shall scale by worker count independently of web traffic |
| NFR-SC3 | The system shall support 200 concurrent generation runs without breaching NFR-P2 |

### 7.6 Usability and Accessibility

| ID | Requirement |
|---|---|
| NFR-U1 | A first-time user shall complete input → export without documentation |
| NFR-U2 | Every failure state shall state the cause and the next action |
| NFR-U3 | WCAG 2.1 AA for colour contrast and keyboard navigation on core flows |
| NFR-U4 | Diagram previews shall be zoomable and pannable |

### 7.7 Maintainability and Cost

| ID | Requirement |
|---|---|
| NFR-M1 | Swapping LLM provider shall require changes only within the LLM Gateway |
| NFR-M2 | Adding a diagram type shall require only a new CPM→source mapper, with no change to ingestion, extraction or document assembly |
| NFR-M3 | Per-run LLM cost shall be recorded and attributable to a user |

---

## 8. Diagram Engine Matrix

This table is a binding design decision arising from constraint C-1 and risk R7.

| Diagram type | Primary engine | Fallback | Notes |
|---|---|---|---|
| Class | PlantUML | Mermaid | Both adequate |
| Entity-Relationship | Mermaid | PlantUML | Mermaid ER output is cleaner |
| Use Case | **PlantUML** | — | **Mermaid has no use case diagram** |
| Sequence | PlantUML | Mermaid | Both adequate |
| Activity | PlantUML | Mermaid flowchart | Mermaid has no true activity diagram; flowchart is an approximation |
| State | PlantUML | Mermaid | Both adequate |
| Component | **PlantUML** | — | Mermaid has no component diagram |
| Deployment | **PlantUML** | — | Mermaid has no deployment diagram |
| Object / Communication / Timing | **PlantUML** | — | Post-V1; PlantUML only |
| Dependency graph | Graphviz | — | V2 |

**Consequence:** PlantUML is a hard dependency and requires JVM-based or hosted rendering. This must be provisioned in infrastructure from M1, not discovered late.

---

## 9. Constraints, Assumptions and Dependencies

### 9.1 Known Limitations of V1

1. Output correctness is not guaranteed; the system produces a reviewed draft, not an authoritative specification.
2. Very short or vague inputs will produce thin models — mitigated by FR-5 rather than by fabrication.
3. Highly domain-specific terminology may be mis-typed as entities and requires user correction at the review gate.
4. No source code is analysed in V1; any claim about an existing codebase is out of scope.

### 9.2 Regulatory and Ethical

- The system shall present generated content as a draft requiring human review (UI-6).
- The system shall not represent generated documents as independently verified or standards-certified.
- User content shall not be used for model training without explicit opt-in.

---

## 10. Verification and Acceptance

### 10.1 Acceptance Test — Core Flow (AT-1)

**Given** a 300-word description of a Library Management System,
**When** the user submits it, confirms the extracted CPM unchanged, selects all diagram types and the default template, and generates,
**Then** within 180 seconds the system shall produce:

- a CPM containing ≥ 5 entities and ≥ 4 relationships;
- 8 rendered diagrams, all syntactically valid;
- byte-identical entity naming across all 8 diagrams;
- a PDF of ≥ 12 pages containing all 8 diagrams as numbered, captioned figures;
- a cover page bearing the user-supplied project name and author;
- an index table whose entries match the actual section and figure numbering;
- a DOCX export whose content matches the PDF.

### 10.2 Verification Method by Requirement Class

| Class | Method |
|---|---|
| Functional (FR-*) | Automated integration tests against a fixed corpus of 20 sample inputs |
| Consistency (FR-10, NFR-Q2) | Automated assertion in the generation pipeline; run fails on violation |
| Performance (NFR-P*) | Load test at 200 concurrent runs; percentile measurement |
| Security (NFR-S*) | Authorisation test suite; dependency and secret scanning in CI |
| Usability (NFR-U*) | Moderated testing with 8 target users before public launch |

---

## 11. Appendices

### Appendix A — Recommended Technology Stack

| Layer | Choice | Rationale |
|---|---|---|
| Frontend | Next.js, TypeScript, Tailwind, shadcn/ui | Matches existing experience; fast to build |
| Diagram canvas (V3) | React Flow | Deferred to V3 |
| Backend | FastAPI (Python) | Best ecosystem for parsing, OCR and future AST work |
| Queue | Redis + worker pool | Simple, sufficient at this scale |
| Database | PostgreSQL with JSONB for CPM payloads | Relational metadata, document-shaped model |
| Object storage | S3-compatible (R2/S3) | Cheap egress on R2 |
| Diagram rendering | PlantUML server (primary), Mermaid CLI (secondary), Graphviz (V2) | Per §8 |
| Document rendering | DOCX via a document library; PDF via headless browser or LibreOffice conversion | DOCX must be first-class, not a PDF byproduct |
| LLM access | Provider-abstracted gateway | Per C-2 |

### Appendix B — Requirements Traceability

| PRD feature | SRS requirements |
|---|---|
| F-01, F-02 | FR-1, FR-2, FR-3 |
| F-03, F-04 | FR-4, FR-5, FR-6, FR-7 |
| F-05, F-06 | FR-8, FR-9, FR-10, FR-11 |
| F-07 | FR-13, FR-16 |
| F-08, F-09, F-10 | FR-17, FR-18, FR-19 |
| F-11, F-12 | FR-14, FR-15 |
| F-13 | FR-12 |
| F-14 | FR-23, FR-24 |

### Appendix C — Deferred Requirements (V2 / V3)

| ID | Requirement | Target |
|---|---|---|
| DR-1 | GitHub repository ingestion via API | V2 |
| DR-2 | ZIP upload and tree-sitter AST parsing | V2 |
| DR-3 | CPM population from parsed code | V2 |
| DR-4 | Folder structure and dependency graphs | V2 |
| DR-5 | API documentation from route definitions | V2 |
| DR-6 | HLD and LLD document types | V2 |
| DR-7 | Interactive canvas editing of diagrams | V3 |
| DR-8 | AI chat over the CPM | V3 |
| DR-9 | Version comparison and architecture drift detection | V3 |
| DR-10 | Team workspaces and collaboration | V3 |
| DR-11 | SSO, private deployment, public API | V3 |
