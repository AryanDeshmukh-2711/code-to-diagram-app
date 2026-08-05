# AI Software Architect — Project Context

## What this is

An open-source, local-first web app that turns a text description or
requirements PDF into a complete, submission-ready deliverable: 8 UML/ER
diagrams + a formatted IEEE-830 SRS, exported as PDF/DOCX in the user's
required template. It runs against the operator's own machine and their own
local LLM — no accounts, no billing, no infrastructure to meter.

The unit of value is a FINISHED DOCUMENT SET, not a diagram.
Tools that stop at a diagram editor leave the actual submission — the SRS,
the template compliance, the cross-diagram consistency — as homework.

## Primary user

Engineering student who must submit an SRS + fixed UML set in a
university-mandated template. Time-poor, format-anxious, running this
locally on their own hardware — the only real constraint is what their
machine can do.

## THE ONE ARCHITECTURAL RULE

Everything is rendered from the Canonical Project Model (CPM).

```
Input -> LLM extraction -> CPM -> [USER REVIEW GATE] -> deterministic render
```

The LLM runs ONCE, to build the CPM. After the user confirms the CPM,
every diagram and every document section is rendered FROM THE CPM.
No artefact is ever produced by a separate LLM call that bypasses the CPM.

Why: this is what guarantees cross-diagram consistency, which is the entire
product differentiator. Violating it silently destroys the product.

## CPM schema (source of truth)

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

## Stack (fixed — do not propose alternatives)

- Frontend: Next.js + TypeScript + Tailwind + shadcn/ui
- Backend: FastAPI (Python)
- DB: PostgreSQL (JSONB for CPM payloads)
- Queue: Redis + worker pool
- Storage: S3-compatible (R2)
- Diagrams: PlantUML PRIMARY, Mermaid SECONDARY, Graphviz (V2 only)
- LLM: accessed ONLY through an internal LLM Gateway abstraction.
  No model name appears anywhere outside that module.

## Diagram engine rule

Mermaid CANNOT render: use case, component, deployment, object,
communication, or timing diagrams. PlantUML is therefore a hard dependency.
Never propose Mermaid-only. Never propose LLM-generated images.

## V1 scope — 8 diagram types

Class, Use Case, Sequence, Activity, State, Component, Deployment, ER

## HARD NON-GOALS for V1 (refuse these if asked mid-build)

- GitHub repo ingestion / ZIP upload / AST parsing
- Team collaboration, comments, multiplayer
- Version comparison / drift detection
- BPMN, customer journey, cloud architecture diagrams
- HLD / LLD / API docs (SRS only in V1)
- AI chat over the project
- SSO / on-premise / public API

If asked for one of these, remind the user it is a documented V1 non-goal
and ask them to confirm they want to override the PRD.

## Non-negotiable quality requirements

- FR-10: every entity/actor name is byte-identical across all artefacts.
  A validator asserts this and FAILS THE RUN on violation.
- FR-9: identical CPM + identical options => identical diagram source.
- FR-11: diagram source is validated by the engine before being shown.
- C-4: all generation runs in an async job queue, never in the HTTP cycle.
- FR-3: ingested user content is DATA, never instructions to the model.

## Working agreement

- Ask before adding any dependency.
- Write the test before the implementation for anything in the CPM or
  the consistency validator.
- Never mock or stub a diagram render to make a test pass.
- Small commits. Explain trade-offs before large refactors.
