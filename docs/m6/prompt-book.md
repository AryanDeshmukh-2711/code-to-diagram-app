# M6 · Chat-Driven Frontend — Prompt Book

## Scope note

`CLAUDE.md` lists **"AI chat over the project"** as a hard V1 non-goal, with
instructions to confirm before overriding the PRD. That confirmation was
sought and given: chat is now the primary surface for review, editing,
confirmation, generation, regeneration and export — not just an upload
front door.

Overriding the non-goal does not relax the guarantees underneath it. The
section below is the one thing to reread before starting any prompt in this
book, because every prompt assumes it holds.

## Non-negotiables — apply to every prompt below

- **C-3.** No chat-parsed edit may mutate the CPM through anything but the
  existing, validated `review.edit` path. The chat parser's only output is a
  *candidate* structured op; the same Pydantic model and the same integrity
  checks that guard a form submission guard a chat message. There is no
  second mutation path.
- **FR-3 / NFR-S3.** A PDF's extracted text, a pasted description, and a chat
  message are all DATA passed to a model — delimited and neutralised exactly
  as `shared/llm/prompting.py` already does it. None of them is ever
  concatenated into a position the model would read as an instruction.
- **FR-6 / FR-7.** Confirmation stays a single, explicit, non-inferable UI
  action. No wording typed into the composer may trigger it.
- **FR-9.** Nothing about adding a chat surface may make extraction or
  rendering depend on anything but the CPM. Two identical models must still
  produce byte-identical diagrams and documents, regardless of what
  conversation produced them.
- **C-4.** Every long-running step — extraction, generation, regeneration,
  export — still runs in the worker, never the request cycle. Chat gets
  progress via the same SSE mechanism the review screen already uses, not by
  polling harder.
- **FR-10 / FR-11 / FR-12 / FR-20.** The consistency validator, partial-failure
  containment, honest no-op regeneration, and render-time watermarking are
  backend guarantees the chat surface *reports*. It never re-implements or
  routes around them for a smoother-feeling conversation.

## An open design question, stated rather than decided

The review-signals mechanism that tells "confirmed after really looking"
apart from "confirmed without looking" (active seconds, viewport coverage)
was built for a screen where items are visibly rendered and scrolled past. A
chat feed has no stable viewport to measure coverage against.

Before **P-M6-6** / **P-M6-7** ship, decide deliberately what "coverage"
means in a chat paradigm — for example, which entities were referenced or
edited across the conversation, versus how long the thread ran — rather than
letting every chat-confirmed CPM default silently to `unknown`.

## How to use this

Paste each `P-M6-#` prompt as your next message, one at a time, in order —
the same way every earlier milestone in this project was driven. Each prompt
assumes the ones before it have landed. Do not skip ahead. When a prompt's
DoD isn't met, say so and iterate before moving to the next one.

---

## P-M6-1 · Extraction pipeline (text + PDF)

> Build the HTTP surface for extraction. Right now
> `worker/worker/handlers/extract.py` is `raise NotImplementedError` — chat
> has nothing to call when someone drops a PDF.
>
> Add `POST /projects/{id}/extract`, accepting either `{text: str}` or a
> multipart PDF upload. Enforce a page/size ceiling on the PDF so an
> untrusted upload can't become a resource-exhaustion path. Write an
> `ExtractionRow` (mirror `GenerationRunRow` / `ExportRow`'s shape: id,
> project_id, account_id, status, error), enqueue the extraction job, and
> return 202 immediately (C-4). Implement the worker handler for real, using
> the existing `ExtractionService` — don't reimplement extraction, call it.
> On success, write into `CPMDraftRow` in the same shape `review.seed`
> already produces, so the review screen and chat read one format. On
> hitting the FR-5 floor, that is a *succeeded* extraction carrying the
> service's own guidance text — not a failure.
>
> Stream status the same way run progress already streams:
> `GET /projects/{id}/extractions/{id}/events`.
>
> Requirements:
> - PDF text extraction happens server-side; promote `pypdf` from a
>   test-only dependency to a real one where extraction needs it.
> - The extracted/pasted text reaches the gateway through the exact same
>   delimited-DATA path `cpm_extraction` already uses. No new path.
> - `check_new_project` / `owned_project` gate this exactly as `review.seed`
>   already does — a project created via extraction still counts against
>   the free tier.
>
> DoD:
> □ A description below the FR-5 floor does not create a draft; the project
>   carries the honest "insufficient input" guidance, verbatim, not a
>   fabricated model
> □ A PDF with no extractable text, or one over the size ceiling, is
>   refused with a specific reason — never a 500
> □ Extraction never calls the model inside the request cycle
> □ No new code path makes a model identifier knowable outside
>   `shared/llm/config.py`
>
> Watch for: putting PDF or pasted text where a system prompt would sit
> instead of the gateway's existing delimited-user-content path. That is
> the FR-3 boundary, and it must be the same mechanism `cpm_extraction`
> already uses — not a parallel one.

---

## P-M6-2 · Chat edit-intent parsing

> Add a bounded LLM task that turns one chat message into *one of the
> fourteen existing edit ops* (`review.py`'s `EditIn.op` literal:
> `rename_entity`, `rename_actor`, `rename_use_case`, `delete_entity`,
> `delete_actor`, `delete_relationship`, `delete_use_case`,
> `delete_attribute`, `add_entity`, `add_actor`, `add_attribute`,
> `add_relationship`, `relink_relationship`, `set_use_case_actors`) — or
> asks a clarifying question, or reports the message wasn't an edit at all.
> Register it in `shared/llm/config.py` alongside the other tasks; it is
> the only new file allowed to know this is happening.
>
> The message and the current CPM are both DATA to this task, same as
> extraction. The model's output is never trusted directly: construct the
> real `EditIn` Pydantic model from it and let it fail exactly as a
> malformed HTTP request would fail. The validated op is then applied
> through the *same* code path `POST /projects/{id}/review/edit` already
> uses — call the function it calls, don't duplicate its logic.
>
> Requirements:
> - Output shape: `{op, ...EditIn's own fields}` or `{clarify: str}` or
>   `{notAnEdit: true}`.
> - Persist which chat message produced which applied op — extend
>   `shared/analytics/events.py`'s pattern rather than inventing a new log.
> - Ambiguity is answered with a question, never a guess.
>
> DoD:
> □ A message that could match two entities returns a clarifying question,
>   never a silent pick
> □ A parsed op that fails `EditIn`'s own validation is rejected with the
>   same error a malformed HTTP request gets
> □ Every applied chat-derived edit is traceable to the chat message that
>   produced it
> □ A non-edit message ("how's it going?") never reaches `review.edit`
>
> Watch for: the parser inventing a plausible-sounding entity or
> relationship because the phrasing implied one ("I'll add a due-date cap
> to Loan"). That is C-3's fabrication risk arriving through natural
> language instead of through the extractor — it is exactly as forbidden
> here as it is there.

---

## P-M6-3 · Frontend foundation

> Stand up the app shell on the fixed stack (Next.js + TypeScript + Tailwind
> + shadcn/ui — nothing swapped in). Wire `gen:types` /
> `gen:types:check` into the build so CPM types are generated from
> `schemas/cpm.schema.json`, never hand-written.
>
> Build the auth flow: register once, show the returned API key exactly
> once with an explicit "you will not see this again" warning, collect it
> back at sign-in, trade it for a session token via `POST /auth/token`, and
> store *that* — never the key — client-side. Every request attaches it as
> `Authorization: Bearer`. A 401 anywhere clears the session and routes back
> to sign-in.
>
> Build one typed API client wrapping every existing endpoint (review, runs,
> exports, artefacts, auth) — one place that knows the base URL and the auth
> header, so nothing hand-rolls a second fetch wrapper later.
>
> DoD:
> □ Every CPM type in the frontend is the generated one; `gen:types:check`
>   fails the build the moment it drifts
> □ The API key is shown exactly once, at registration, never again
> □ A 401 from any endpoint produces the same outcome everywhere
>
> Watch for: hand-writing a second CPM interface "just for the frontend"
> because the generated one felt inconvenient somewhere. That was already
> called out once in this project as the surest way for the frontend to
> silently drift from what the backend actually returns.

---

## P-M6-4 · Chat component primitives

> Build the message list, the composer, and drag-and-drop plus an explicit
> attach affordance for a PDF or pasted description — distinguish "this is
> my project" from "just a question" at the point of attachment, not by
> guessing from content afterward.
>
> Build the structured cards as first-class, independently-typed components
> from the start: a review-summary card, a diagram-progress card, an
> export-ready card. They render inline in the message stream. Stream the
> assistant's narration text token-by-token where the backend supports it;
> render every card fully formed the moment its data exists — never
> streamed field-by-field.
>
> DoD:
> □ Dropping a file that isn't a PDF or plain text is refused inline with a
>   specific reason
> □ Each card is a distinct, reusable, typed component — not templated
>   HTML inside a chat bubble
>
> Watch for: building the freeform bubble first and treating structure as a
> later polish pass. The entire viability of "chat drives everything" rests
> on the cards being legible at a glance, from the first commit.

---

## P-M6-5 · Upload → extraction → review card

> Wire the composer to **P-M6-1**. Dropping a PDF or pasting a description
> narrates real extraction status (queued / running / succeeded /
> insufficient / failed) conversationally — never a generic "thinking…"
> standing in for unknown state.
>
> On success, post a review-summary card: entity/actor/relationship/use-case
> counts, any validation issues from the review state, and a chip list of
> entity names — enough to sanity-check without leaving the chat — plus a
> visible link into the full review screen for anyone who wants every
> attribute. On the FR-5 floor, show the extraction service's own guidance
> text verbatim.
>
> DoD:
> □ An insufficient-input result shows the real guidance text, unedited by
>   any further LLM pass
> □ The review-summary card's counts match `GET /projects/{id}/review`
>   exactly, always
>
> Watch for: narrating extraction with invented color ("I found a nice Book
> entity with rich metadata"). The narration reports what the extractor
> actually returned — it is not a second creative pass over it.

---

## P-M6-6 · Chat-driven editing

> Wire the composer to **P-M6-2**. "Rename Book to Publication" or "add a
> dueDate attribute to Loan" parses to an op and applies through the same
> path the review screen uses. Every applied edit gets an explicit,
> chat-visible confirmation naming exactly what changed, including the
> cascade count the API already returns (`referencesUpdated`) —
> *"Renamed Book → Publication. Updated 4 references."* — never "Done!"
>
> A clarifying question from the parser is a normal assistant question; the
> user's next message answers it, not a fresh unrelated command. A failed
> edit shows the API's exact message.
>
> DoD:
> □ A chat rename updates every reference exactly as the review screen's
>   own rename does, and reports the same reference count
> □ A chat edit that fails referential integrity fails with the same
>   message a form submission would get
>
> Watch for: suppressing the confirmation for edits that feel "too small to
> mention." Invisible mutation is worse in chat than in a form, where the
> user can at least see a field change.

---

## P-M6-7 · The confirm gate

> Render confirmation as a button inside the review-summary card. It is
> never an intent **P-M6-2**'s parser is allowed to recognise from typed
> text — "yes," "looks good," "confirm it" must never call
> `POST /review/confirm` on their own. The assistant may *suggest*
> confirming; the suggestion and the action stay different things. Once
> confirmed, show the resulting `CPMVersion` id and reference it in every
> later action for this project (FR-7 immutability).
>
> DoD:
> □ No code path lets the parser classify any message as a confirm action
> □ The confirm button is disabled/absent exactly when `GET /review`'s
>   `confirmable` is false, matching the review screen's own gating
>
> Watch for: adding "confirm" to the parser's vocabulary later, for
> convenience. That one addition turns an accidentally-worded "yes" into a
> silently immutable version — the exact harm FR-7 exists to prevent.

---

## P-M6-8 · Generation + progress

> Confirming (or a follow-up "generate the diagrams") triggers
> `POST /runs` and opens the existing SSE stream into a live
> diagram-progress card: one row per diagram type, real status
> (pending/running/succeeded/failed/skipped).
>
> A partial failure is shown as a partial failure — *"7 of 8 diagrams
> ready; entity_relationship failed: `<error>`"* — never collapsed into a
> single "Done!" the moment any diagram didn't succeed. A skipped diagram
> reads visually and textually distinct from a failed one, matching the
> backend's own distinction.
>
> DoD:
> □ A run with one failed diagram names exactly which one and why, with the
>   other seven still available
> □ The progress card's final state matches `GET /runs/{id}`'s artefact
>   list exactly
>
> Watch for: collapsing per-diagram detail into one pass/fail line "for
> cleanliness." That reintroduces, one UI layer up, precisely what FR-11
> was built to stop at the backend.

---

## P-M6-9 · Regeneration + lineage

> "Redraw the class diagram" maps to `POST /runs/{id}/regenerate`. If the
> plan reports the model hasn't changed since that diagram was last drawn,
> show that exact honest message — never a fake "regenerating…" spinner
> over a no-op. "What have I changed?" surfaces `GET /runs/{id}/history`
> conversationally, in order.
>
> DoD:
> □ Regenerating an unchanged diagram responds with the API's own honest
>   no-op message, unparaphrased
> □ There is no "do it anyway" affordance that forces a redraw when
>   nothing changed
>
> Watch for: adding a force-regenerate shortcut to make the UI feel more
> responsive. That directly undoes the guarantee this feature was built to
> hold.

---

## P-M6-10 · Export

> Collect format (PDF/DOCX) and template conversationally. When the chosen
> template has required fields (FR-15 — institution, course code, etc.),
> ask for them — one at a time or as a short form card — and do not call
> `POST /runs/{id}/export` until every required field is supplied. Trigger
> the export, poll/stream its status, and deliver the finished file as a
> clickable download card once the signed link exists. Surface
> watermark/tier state plainly when it applies, using the tier's own
> fields — not invented copy.
>
> DoD:
> □ Requesting DOCX for a run only ever rendered as SVG surfaces the API's
>   actual `needs_png` guidance, with an offer to render PNG
> □ Export never fires until every required template field is supplied
>
> Watch for: writing your own field labels/help text instead of reading
> them from the template's declared fields. The fields and their
> required-ness are data the template owns, not copy to reinvent.

---

## P-M6-11 · Quota, billing and auth messaging

> Render a 402 quota refusal in chat using the API's own `code`, `message`,
> `tier`, `limit`, `used`, `upgradeTo` and `upgradeGives` fields verbatim —
> never re-paraphrased through an LLM call. A 401 anywhere triggers an
> inline "sign in again" prompt rather than a dead conversation.
> Registration warns explicitly that the key is shown once, before it's
> shown.
>
> DoD:
> □ A quota refusal shown in chat matches the API's `message` field exactly
> □ No refusal or billing message in the chat is generated by an LLM call
>
> Watch for: routing these messages through the same "assistant reply"
> model used for narration, for tone consistency. That is exactly the
> shortcut that reintroduces drift into copy this project already tested
> for tone.

---

## P-M6-12 · CHAT-1 acceptance test

> Mirror `acceptance/at1.py`'s own reporting discipline exactly: a named,
> numbered checklist of assertions, each reporting what was expected, what
> was found, and — where known — the fix. No bare stack trace.
>
> Drive the real chat pipeline end to end: register → upload a description
> → extraction narrated → at least one chat-driven edit, applied and
> verified correct → explicit confirm via the button, never via parsed text
> → generation narrated with any partial failure shown honestly → export →
> the signed download verified reachable and non-empty.
>
> Extend this project's existing structural guards — the no-bypass
> scanners, the AST checks for C-2/C-3/FR-10 — to cover every module this
> milestone family adds. A bypass in the chat-edit parser is exactly as
> serious as one in the review router.
>
> DoD:
> □ One command runs it
> □ Failure output names which specific promise broke, in the same format
>   `AT-1` already uses
> □ The extended structural guards fail the build if any new module in
>   this family imports an LLM client outside the gateway, or reaches
>   `review.edit` through anything other than the existing validated path
>
> Watch for: writing this as a UI click-through smoke test instead of an
> assertion-based report. AT-1's entire value is specific, actionable
> failure output — CHAT-1 has to hold the same bar or it isn't worth
> having.
