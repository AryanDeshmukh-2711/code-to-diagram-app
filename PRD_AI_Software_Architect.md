# Product Requirements Document

**Product:** AI Software Architect (working name; earlier internal name — UML Studio)
**Author:** Aryan Vijay Deshmukh
**Version:** 1.0
**Date:** 30 July 2026
**Status:** Draft for review

> **Note (2026-08-05):** This document was written for the project's original
> commercial-SaaS phase. The project has since pivoted to an open-source,
> local-first, single-user tool — it runs against the operator's own machine
> and their own LLM, with no accounts and no billing. The specific
> pricing/tier/account references below have been corrected to match; the
> surrounding narrative (competitive positioning, hosted-infrastructure
> framing) describes that earlier phase and has not been rewritten. CLAUDE.md
> is the current source of truth for product direction.

---

## 1. Summary

A web platform that turns a project description, requirement document, or codebase into a **complete, submission-ready software engineering deliverable** — the full set of UML diagrams plus the accompanying SRS/design document, exported in the exact format the user has to hand in or ship.

The unit of value is **not a diagram**. It is a finished document set that would otherwise take 8–20 hours to assemble by hand.

---

## 2. Problem

Producing software engineering artefacts is high-effort, low-creativity work that is mandatory in two contexts:

| Context | Artefact required | Typical manual effort |
|---|---|---|
| Academic (final-year project, lab file, mini-project) | SRS + 6–9 UML diagrams in a fixed university template | 10–20 hours |
| Professional (client handover, internal design review, tender) | HLD/LLD + architecture diagrams + API docs | 8–15 hours |

The work is repetitive, the format is rigid, and the output is judged on **completeness and consistency**, not creativity. Existing tools solve the drawing step and leave the assembly step entirely to the user.

---

## 3. Market Reality (read this before building)

This section exists to prevent building something that already exists for free.

### 3.1 What is already solved and cannot be a differentiator

- **Text → diagram.** Eraser DiagramGPT, Miro AI, GitMind, Visual Paradigm's AI wizard, Cloudairy, ChatUML and RapidChart all generate UML from a prompt. Frontier LLMs emit valid Mermaid and PlantUML natively with no product wrapper at all.
- **Repo → architecture diagram / wiki.** DeepWiki (Cognition) pre-indexes 50,000+ public GitHub repos into browsable wikis with Q&A, free. GitDiagram converts any repo URL into an interactive architecture diagram. Swark does the same inside VS Code. Multiple open-source Claude/agent skills produce polished architecture diagrams from a repo.
- **Docs that stay in sync with code.** Mintlify's agent, Swimm's code-coupled docs and CI staleness checks, and Promptless occupy this space with real funding and real customer logos.

**Conclusion:** "AI that makes diagrams from code" is a commodity in 2026. Entering as a better version of that loses.

### 3.2 What is not solved — the wedge

No tool delivers **the finished, format-compliant artefact**:

- No tool outputs an SRS in a specific university's mandated template with the correct cover page, certificate page, index table, headers and footers.
- No tool guarantees **cross-artefact consistency** — that the class diagram, ER diagram, sequence diagrams and SRS section 3 all describe the *same* entity set with the same names.
- No tool produces the *complete required set* for a submission. They produce one diagram at a time and leave the user to assemble, renumber, and reformat.
- Generic tools export PNG/SVG. Academic and enterprise submissions need a paginated document.

**Positioning statement:** everyone else sells a diagram editor. This sells a **finished deliverable**.

### 3.3 Why incumbents will not take this

Formatting to a specific institution's template is unglamorous, low-margin per user, and requires India-specific (or region-specific) distribution. Mintlify and Cognition are chasing enterprise developer platforms. This niche is structurally unattractive to them and structurally attractive to a solo founder with direct access to the user base.

---

## 4. Goals and Non-Goals

### 4.1 Goals (V1)

| ID | Goal | Measure |
|---|---|---|
| G1 | Produce a complete, consistent diagram set from a text/PDF input | ≥ 8 diagram types from one input, sharing one entity model |
| G2 | Export a submission-ready document | PDF/DOCX with cover, index, numbered figures, headers/footers |
| G3 | Make output editable without redrawing | User edits entity model, all diagrams regenerate |
| G4 | Be fast enough to feel magical | Full set generated in < 3 minutes |

### 4.2 Explicit Non-Goals (V1)

These are deferred deliberately. Each one is a project in itself.

- ❌ GitHub repository ingestion and large-codebase understanding
- ❌ ZIP / source code upload and AST parsing
- ❌ Team collaboration, real-time multiplayer, comments
- ❌ Version comparison / architecture drift detection
- ❌ BPMN, customer journey maps, cloud architecture diagrams
- ❌ Multi-language code support
- ❌ On-premise / SSO / enterprise deployment
- ❌ AI chat over the project

**Rationale:** the original vision document specifies 11 UML types, 6 architecture types, BPMN, folder/dependency graphs, and 4 documentation types, across 5 input modes, with editing, collaboration and versioning. That is a 18–24 month build for a team. V1 must be shippable by one person in roughly 8 weeks.

---

## 5. Target Users

### 5.1 Primary — "Submission-driven student" (V1 focus)

Final-year / pre-final-year engineering student in a CS/IT programme. Must submit an SRS and a fixed set of UML diagrams for a mini-project or capstone, in a template the department mandates. Time-poor, format-anxious, running the tool locally against their own machine and their own LLM. Highly clustered — one campus contains thousands of them, and they share tools by word of mouth.

**Why start here:** urgent, recurring, deadline-driven, easy to reach, and the deliverable format is knowable and finite.

### 5.2 Secondary — "Freelancer / small agency" (V2)

Delivers client projects and must ship an HLD/LLD or architecture pack alongside the code. Values speed and professional appearance over rigour. Will pay ₹1500–3000/month if it saves a day per project.

### 5.3 Tertiary — "Small product team" (V3)

Needs living architecture documentation. This is where DeepWiki/Swimm/Mintlify compete directly — enter only with a differentiated wedge and never as the entry market.

---

## 6. Product Scope

### 6.1 V1 — "The Deliverable Engine" (target: 8 weeks)

Input is **text prompt or requirement PDF only.**

1. **Input & extraction** — prompt box or PDF upload; extract requirements, actors, entities.
2. **Canonical project model** — a single structured intermediate representation (entities, attributes, relationships, actors, use cases, flows) that *every* artefact is rendered from. This is the core technical asset.
3. **Model review screen** — user confirms/edits entities and relationships **before** any diagram is generated. This is the quality control gate and the main defence against LLM hallucination.
4. **Diagram generation** — Class, Use Case, Sequence, Activity, State, Component, Deployment, ER.
5. **Document generation** — SRS following IEEE 830 / ISO-IEC-IEEE 29148 structure, with generated diagrams embedded as numbered figures.
6. **Template system** — user picks a template (or uploads their institution's cover/certificate/index pages) and the document is rendered into it.
7. **Export** — PDF, DOCX, PNG/SVG per diagram, PlantUML/Mermaid source.

### 6.2 V2 — "Code Input" (+8 weeks, only if V1 retains)

GitHub repo and ZIP ingestion; AST/tree-sitter parsing to populate the canonical model; folder structure and dependency graphs; API documentation from route definitions.

### 6.3 V3 — "Platform"

Interactive canvas editing, AI chat over the project model, version comparison, team workspaces, architecture review suggestions.

---

## 7. Functional Requirements

Priority: **P0** = V1 blocker, **P1** = V1 desirable, **P2** = post-V1.

| ID | Requirement | Priority |
|---|---|---|
| F-01 | Accept a free-text project description (min 50, max 20,000 chars) | P0 |
| F-02 | Accept a PDF upload (≤ 25 MB) and extract text, including scanned PDFs via OCR fallback | P0 |
| F-03 | Derive a canonical project model: entities, attributes, relationships, actors, use cases, flows | P0 |
| F-04 | Present the canonical model for user review and editing before generation | P0 |
| F-05 | Generate ≥ 8 diagram types from the confirmed model | P0 |
| F-06 | Guarantee naming/entity consistency across all generated diagrams | P0 |
| F-07 | Generate an IEEE-830-structured SRS with diagrams embedded as numbered figures | P0 |
| F-08 | Export PDF and DOCX | P0 |
| F-09 | Export individual diagrams as PNG and SVG | P0 |
| F-10 | Export diagram source (PlantUML / Mermaid) | P1 |
| F-11 | Template picker with ≥ 3 built-in academic formats | P1 |
| F-12 | Custom template upload (cover page, certificate, index, header/footer text) | P1 |
| F-13 | Regenerate a single diagram without regenerating the whole set | P1 |
| F-14 | Project save / reload / duplicate | P1 |
| F-15 | Post-generation manual diagram editing on a canvas | P2 |
| F-16 | GitHub repository ingestion | P2 |
| F-17 | ZIP / source upload and AST parsing | P2 |
| F-18 | AI chat over the project model | P2 |

### 7.1 Acceptance criteria for the core flow

Given a 300-word description of a "Library Management System", the system shall, within 180 seconds, produce: a canonical model containing ≥ 5 entities; 8 rendered diagrams in which every entity name is spelled identically; and a PDF SRS of ≥ 12 pages containing all 8 diagrams as numbered, captioned figures, with a title page bearing the user-supplied project and author name.

---

## 8. Key User Flow

```
Landing
  └─> New Project
        └─> Choose input: [Paste description] or [Upload PDF]
              └─> AI extracts → CANONICAL MODEL REVIEW  ◀── quality gate
                    ├─ user edits entity names, attributes, relationships
                    └─> Select diagram types (all pre-selected)
                          └─> Select document template
                                └─> Generate (progress per artefact)
                                      └─> Result page
                                            ├─ preview all diagrams
                                            ├─ regenerate individual diagram
                                            └─> Export: PDF / DOCX / PNG / SVG / source
```

The **canonical model review** step is the product's differentiator and must not be skippable in V1. It converts an unreliable one-shot generation into a reviewed, deterministic render.

---

## 9. Success Metrics

| Metric | V1 target (first 90 days) |
|---|---|
| Activation — % of signups reaching a completed export | ≥ 35% |
| Time to first export | < 6 minutes median |
| Diagram set acceptance — % exported without regeneration | ≥ 60% |
| Retention — % returning within 60 days | ≥ 20% |
| Referral coefficient within a single campus | ≥ 0.3 |

**Kill criterion:** if activation is below 20% after 300 signups, the canonical-model step is too heavy or the output quality is unacceptable. Fix or stop before building V2.

---

## 10. Monetisation

**Historical.** This section described a commercial-SaaS pricing model from an
earlier phase of the project. The project has since pivoted to an
open-source, local-first tool: it runs against the operator's own machine
and their own local LLM, so there is no infrastructure cost to meter and
nobody to bill. See CLAUDE.md for the current product direction.

---

## 11. Risks

| # | Risk | Severity | Mitigation |
|---|---|---|---|
| R1 | Output is plausible but wrong; user submits it and is penalised | **High** | Mandatory model-review gate; never present output as authoritative; validation pass on diagram syntax before render |
| R2 | Commodity pressure — free tools reach parity on generation | **High** | Compete on the deliverable and template compliance, not on generation quality |
| R4 | Scope creep back toward the full original vision | **High** | Non-goals in §4.2 are contractual; V2 requires meeting the V1 kill criterion first |
| R5 | Academic integrity objection from institutions | Medium | Position as a drafting and formatting assistant; user-editable model; maintain an audit trail of user edits |
| R6 | Large-codebase understanding proves unreliable in V2 | Medium | Deferred entirely out of V1; V2 begins with a narrow language scope (one language, one framework) |
| R7 | Diagram engines cannot render some required UML types | Medium | Engine matrix decided up front — see SRS §8; PlantUML primary, Mermaid secondary |

---

## 12. Milestones

| Phase | Duration | Exit criterion |
|---|---|---|
| M0 — Validation | 1 week | 15 target users interviewed; 5 real university templates collected |
| M1 — Model + 3 diagrams | 2 weeks | Prompt → canonical model → Class, ER, Use Case rendering |
| M2 — Full diagram set | 2 weeks | All 8 types rendering consistently from one model |
| M3 — Document engine | 2 weeks | IEEE-830 SRS assembled with embedded figures; PDF + DOCX export |
| M4 — Templates + polish | 1 week | 3 built-in templates; custom template upload |
| M5 — Private beta | 1 week | 30 users on one campus; measure activation |
| M6 — Public launch | — | Kill criterion assessed before any V2 work begins |

---

## 13. Open Questions

1. Does the canonical-model review step increase output trust enough to justify the added friction — or does it cause drop-off? **Test in M5.**
2. Is PDF requirement input actually used, or do users only ever paste text? If the latter, drop PDF from V1 and save a week.
3. Which specific university templates cover the largest addressable population? Collect real files in M0.
4. Is DOCX export or PDF export the true must-have? DOCX allows the student to edit afterwards and may matter more.

---

## 14. Appendix — Deviations from the original vision document

| Original | Revised | Reason |
|---|---|---|
| 5 input types | 2 in V1 (text, PDF) | Code ingestion is the hardest 80% of effort for the smallest V1 value |
| 11 UML + 6 architecture + BPMN + 2 dev diagrams | 8 UML/ER types | Coverage beyond this is unused by the primary persona |
| SRS + HLD + LLD + API Docs | SRS only in V1 | One document done correctly beats four done approximately |
| "GPT-5.5, Claude, Gemini" named in stack | Provider-abstracted model layer | Never hardcode a model; route by task and cost |
| Mermaid, PlantUML, Graphviz, D2 all listed | PlantUML primary, Mermaid secondary | Mermaid cannot render use case, object, communication, timing or true deployment diagrams |
| Collaboration, versioning, review in scope | Deferred to V3 | Not needed to prove the core hypothesis |
