"use client";

import { useEffect, useRef, useState } from "react";

import type { Attachment } from "@/components/chat/Composer";
import { Composer } from "@/components/chat/Composer";
import { MessageList } from "@/components/chat/MessageList";
import type { ChatMessage, ConfirmedVersion } from "@/components/chat/types";
import { type ChatEdit, sendChatMessage, streamChatEdit } from "@/lib/chat";
import { chatEditOutcomeNarration, chatEditProgressNarration } from "@/lib/chatEditNarration";
import { _resetUnauthorizedHandler, _setUnauthorizedHandler, ApiError } from "@/lib/client";
import { exportOutcomeNarration, exportProgressNarration } from "@/lib/exportNarration";
import { looksLikeExportRequest, parseExportFormat } from "@/lib/exportIntent";
import {
  getExport,
  listTemplates,
  requestExport,
  type ExportResult,
  type TemplateSummary,
} from "@/lib/exports";
import {
  continueExtraction,
  extractFromPdf,
  extractFromText,
  streamExtraction,
  type Extraction,
} from "@/lib/extraction";
import { looksLikeGenerateRequest } from "@/lib/generateIntent";
import { historyNarration } from "@/lib/historyNarration";
import { looksLikeHistoryRequest } from "@/lib/historyIntent";
import { extractionOutcomeNarration, extractionProgressNarration } from "@/lib/narration";
import { quotaRefusal } from "@/lib/quota";
import { confirmReview, loadReview, type Review, ReviewRefused } from "@/lib/review";
import { regeneratePlanNarration } from "@/lib/regenerateNarration";
import { looksLikeRegenerateRequest } from "@/lib/regenerateIntent";
import { runOutcomeNarration, runProgressNarration } from "@/lib/runNarration";
import {
  getRun,
  regenerate,
  runHistory,
  type Run,
  type RegenerateResult,
  startRun,
  streamRun,
} from "@/lib/runs";
import { clearSession } from "@/lib/session";

function newId(): string {
  return typeof crypto !== "undefined" && crypto.randomUUID
    ? crypto.randomUUID()
    : `m_${Date.now()}_${Math.random().toString(36).slice(2)}`;
}

function pdfProjectName(file: File): string {
  return file.name.replace(/\.pdf$/i, "").trim() || "New project";
}

/** How often an in-flight export is re-checked. No SSE stream exists for
 * exports (unlike runs), so this is a plain poll — infrequent enough not to
 * hammer the API, frequent enough that "assembling…" doesn't sit stale. */
const EXPORT_POLL_MS = 900;

type PendingClarification = {
  /** Everything said so far in this back-and-forth, so the parser sees the
   * whole exchange rather than just the latest, context-free reply. */
  contextText: string;
  /** The parser's own question, restated so the combined message reads as a
   * real exchange rather than two unrelated sentences stapled together. */
  question: string;
};

/**
 * Wires the composer to real extraction (P-M6-1), real chat edit-intent
 * parsing (P-M6-2), the confirm gate (P-M6-7), diagram generation (P-M6-8),
 * regeneration + lineage (P-M6-9), export (P-M6-10), and quota/billing/auth
 * messaging (P-M6-11).
 *
 * Everything narrated here comes straight off the row the backend returns
 * for whichever job is in flight: lib/narration.ts, lib/chatEditNarration.ts,
 * lib/runNarration.ts and lib/regenerateNarration.ts are the only things
 * that turn a row into a sentence, and none of them invent detail the row
 * does not carry (FR-9, C-3, FR-10/11/12/20). A partial run failure names
 * exactly which diagram failed and why; a no-op regeneration shows the
 * plan's own `reason` completely unedited, and — because that decision is
 * synchronous — never after a "regenerating…" message that would have been
 * a lie the moment it appeared.
 *
 * A clarifying question is answered, not restarted: while
 * `pendingClarification` is set, the next message sent is not the user's
 * raw reply but that reply appended to the whole exchange so far, so the
 * single-message parser (P-M6-2 has no conversation history of its own) has
 * enough context to resolve what "it" or "the second one" meant.
 *
 * Confirming is FR-6/FR-7's one non-negotiable: `onConfirmProject` is wired
 * to exactly one control, the confirm button `MessageList` renders inside a
 * review-summary card (see ReviewSummaryCard's own docstring). Nothing in
 * `onSend` can reach it — a typed "yes" is sent to the same parser
 * `sendChatMessage` always uses, whose vocabulary (shared/chat/intent.py)
 * has no confirm-shaped op to recognise it as, pinned by
 * shared/tests/test_confirm_is_not_chat_parseable.py.
 *
 * "Generate the diagrams", "redraw the class diagram", "what have I
 * changed?" and "export this as a PDF" are each recognised the same
 * deliberate way "attach" is (P-M6-4): a small local check
 * (lib/generateIntent.ts, lib/regenerateIntent.ts, lib/historyIntent.ts,
 * lib/exportIntent.ts) before a message ever reaches the edit-intent parser,
 * never new ops added to that parser's vocabulary. Nothing here offers a way
 * to make an unchanged diagram redraw anyway — a structural test in this
 * module's lib/ directory pins that.
 *
 * Export (P-M6-10) collects format and template conversationally rather
 * than assuming either: a format named in the same message is used
 * immediately, an unnamed one is asked for and the next message is read for
 * just that answer, falling through to the normal pipeline unchanged if it
 * names none. The template — and that template's own required fields
 * (FR-15) — are collected by one card, ExportSetupCard, whose Submit stays
 * disabled until every required field is filled; `POST .../export` is never
 * called before that (see its own docstring). A `needs_png` failure and the
 * offer to fix it are the backend's own guidance and this product's existing
 * generation path respectively — nothing here reimplements either.
 *
 * An FR-5 "insufficient input" outcome does not end the conversation either:
 * `pendingExtractionRetry` names the attempt that came up short, and the
 * next chat message is read as the detail the user is adding rather than an
 * edit request or a fresh attach — combined server-side with what that
 * attempt already had (`POST .../extract`'s `previousExtractionId`) so nothing
 * typed or uploaded earlier has to be repeated. Still one model call per
 * attempt; a retry is a new attempt; nothing here re-runs extraction twice on
 * the same text or invents entities the description does not support.
 *
 * Quota, billing and auth messages (P-M6-11) are canonical API output, not
 * narration: `reportApiError` is the one place every catch block in this
 * component funnels through, and it never lets a 402 or a 401 reach the
 * generic "assistant said something went wrong" bubble every other error
 * does. A 402 becomes a QuotaRefusalCard carrying `code`, `message`, `tier`,
 * `limit`, `used`, `upgradeTo` and `upgradeGives` exactly as
 * `billing/quota.py` wrote them (lib/quota.ts). A 401 becomes a
 * SessionExpiredCard rather than the dead conversation a silent
 * `window.location.href` redirect would leave behind: this component
 * overrides `client.ts`'s default unauthorized handler for as long as it is
 * mounted specifically so that redirect never fires out from under an
 * in-progress action, and restores the default on unmount.
 */
export function ChatSession({ projectId }: { projectId: string }) {
  const [messages, setMessages] = useState<ChatMessage[]>(() => [
    {
      id: newId(),
      role: "assistant",
      kind: "narration",
      source:
        "Drop a PDF or paste a description to get started, or tell me what to change in a model already in review.",
      at: new Date().toISOString(),
    },
  ]);
  const [busy, setBusy] = useState(false);
  const [pendingClarification, setPendingClarification] = useState<PendingClarification | null>(
    null,
  );
  const [confirmingId, setConfirmingId] = useState<string | null>(null);
  const [latestConfirmedVersion, setLatestConfirmedVersion] = useState<ConfirmedVersion | null>(
    null,
  );
  const [latestRunId, setLatestRunId] = useState<string | null>(null);
  const [awaitingExportFormat, setAwaitingExportFormat] = useState(false);
  const [pendingExtractionRetry, setPendingExtractionRetry] = useState<{
    extractionId: string;
  } | null>(null);
  const [exportSubmittingId, setExportSubmittingId] = useState<string | null>(null);
  const activeStream = useRef<(() => void) | null>(null);

  useEffect(() => {
    // While this session is mounted, a 401 must not silently navigate the
    // page away — that is the "dead conversation" the DoD names. Clearing
    // the stale token is still correct (nothing should keep sending it);
    // only the redirect is suppressed, in favour of reportApiError's own
    // inline SessionExpiredCard.
    _setUnauthorizedHandler(() => clearSession());
    return () => {
      activeStream.current?.();
      _resetUnauthorizedHandler();
    };
  }, []);

  function append(message: ChatMessage) {
    setMessages((current) => [...current, message]);
  }

  function updateNarration(id: string, source: string) {
    setMessages((current) =>
      current.map((message) =>
        message.id === id && message.kind === "narration" ? { ...message, source } : message,
      ),
    );
  }

  function updateRun(id: string, run: Run) {
    setMessages((current) =>
      current.map((message) =>
        message.id === id && message.kind === "diagram-progress" ? { ...message, run } : message,
      ),
    );
  }

  /** Every catch block in this component funnels through here (P-M6-11).
   * `narrationId`, when given, names the in-flight "…ing" bubble this action
   * already posted — a 402 or 401 turns it into a short, generic pointer,
   * never the canonical message itself, which appears in full in the card
   * appended right after. Routing a quota refusal or a session expiry
   * through the same "assistant said something went wrong" text every other
   * error uses is exactly the Watch For this step names: that shortcut is
   * what already reintroduced copy drift once. */
  function reportApiError(narrationId: string | null, error: unknown, fallback: string) {
    const refusal = quotaRefusal(error);
    const expired = error instanceof ApiError && error.status === 401;

    if (refusal || expired) {
      if (narrationId) updateNarration(narrationId, "That didn't go through — see below.");
      append(
        refusal
          ? { id: newId(), role: "assistant", kind: "quota-refusal", refusal, at: new Date().toISOString() }
          : {
              id: newId(),
              role: "assistant",
              kind: "session-expired",
              returnTo: `/projects/${projectId}/chat`,
              at: new Date().toISOString(),
            },
      );
      return;
    }

    const message = error instanceof ApiError ? error.message : fallback;
    if (narrationId) {
      updateNarration(narrationId, message);
    } else {
      append({ id: newId(), role: "assistant", kind: "narration", source: message, at: new Date().toISOString() });
    }
  }

  /** Re-fetches the live review state and posts a fresh card. Called after
   * every mutation (a successful extraction, a successful chat edit) so the
   * confirm button on the newest card is always gated by a `confirmable`
   * value fetched after that mutation, never a snapshot an edit since made
   * stale. */
  async function postReviewCard() {
    const review = await loadReview(projectId);
    append({
      id: newId(),
      role: "assistant",
      kind: "review-summary",
      review,
      at: new Date().toISOString(),
    });
  }

  /** Posts a diagram-progress card for an already-started run and follows it
   * to completion over SSE (C-4) — shared by a fresh generation and a
   * regeneration's child run, so there is exactly one place that turns a Run
   * into a card and one place that decides when it is finished. */
  function trackRun(run: Run, narrationId: string) {
    setLatestRunId(run.runId);
    const cardId = newId();
    append({ id: cardId, role: "assistant", kind: "diagram-progress", run, at: new Date().toISOString() });
    updateNarration(narrationId, runProgressNarration(run));

    activeStream.current = streamRun(run.runId, (snapshot) => {
      updateRun(cardId, snapshot);

      if (snapshot.status === "pending" || snapshot.status === "running") {
        updateNarration(narrationId, runProgressNarration(snapshot));
        return;
      }

      // A partial failure is reported as one, in full — see runNarration.ts.
      updateNarration(narrationId, runOutcomeNarration(snapshot));
      activeStream.current = null;
      setBusy(false);
    });
  }

  /** POST /runs. Called right after a successful confirm, from a "generate
   * the diagrams" follow-up, and from a needs-png card's "Render PNG" —
   * `format` defaults to the backend's own default (svg) unless a card asks
   * for a specific one. */
  async function runDiagramGeneration(cpmVersionId: string, format?: string) {
    const narrationId = newId();
    append({
      id: narrationId,
      role: "assistant",
      kind: "narration",
      source: "Queued — I'll start drawing in just a moment.",
      at: new Date().toISOString(),
    });

    setBusy(true);

    let run: Run;
    try {
      run = await startRun(format ? { projectId, cpmVersionId, format } : { projectId, cpmVersionId });
    } catch (error) {
      reportApiError(narrationId, error, "Something went wrong starting that.");
      setBusy(false);
      return;
    }

    trackRun(run, narrationId);
  }

  /** "Redraw the class diagram" -> POST /runs/{id}/regenerate. The plan
   * comes back synchronously either way, so the narration it produces is the
   * first and only thing said before anything that might actually be a
   * no-op — never a spinner shown ahead of an answer already known. */
  async function onRegenerateDiagram(diagramType: string) {
    if (!latestRunId) {
      append({
        id: newId(),
        role: "assistant",
        kind: "narration",
        source: "Nothing's been generated yet — generate the diagrams first.",
        at: new Date().toISOString(),
      });
      return;
    }

    setBusy(true);

    let plan: RegenerateResult;
    try {
      plan = await regenerate(latestRunId, { diagramType });
    } catch (error) {
      reportApiError(null, error, "Something went wrong regenerating that.");
      setBusy(false);
      return;
    }

    const narrationId = newId();
    append({
      id: narrationId,
      role: "assistant",
      kind: "narration",
      source: regeneratePlanNarration(plan),
      at: new Date().toISOString(),
    });

    if (!plan.changed || !plan.runId) {
      // The plan itself is the whole story on a no-op — nothing to track.
      setBusy(false);
      return;
    }

    try {
      const run = await getRun(plan.runId);
      trackRun(run, narrationId);
    } catch (error) {
      reportApiError(narrationId, error, "Something went wrong fetching that run.");
      setBusy(false);
    }
  }

  /** "What have I changed?" -> GET /runs/{id}/history, read back in the same
   * oldest-first order the backend already returns it in. */
  async function onShowHistory() {
    if (!latestRunId) {
      append({
        id: newId(),
        role: "assistant",
        kind: "narration",
        source: "Nothing's been generated yet, so there's no history.",
        at: new Date().toISOString(),
      });
      return;
    }

    try {
      const entries = await runHistory(latestRunId);
      append({
        id: newId(),
        role: "assistant",
        kind: "narration",
        source: historyNarration(entries),
        at: new Date().toISOString(),
      });
    } catch (error) {
      reportApiError(null, error, "Something went wrong fetching the history.");
    }
  }

  /** "Export this as a PDF" -> collects the template and its own required
   * fields via one ExportSetupCard. GET /templates is the only thing this
   * calls before that card exists — never a guess at what a tier or
   * template allows. */
  async function beginExport(format: "pdf" | "docx") {
    if (!latestRunId || !latestConfirmedVersion) {
      append({
        id: newId(),
        role: "assistant",
        kind: "narration",
        source: "Nothing's been generated yet — generate the diagrams first.",
        at: new Date().toISOString(),
      });
      return;
    }

    setBusy(true);
    let templates: TemplateSummary[];
    try {
      templates = await listTemplates();
    } catch (error) {
      reportApiError(null, error, "Something went wrong listing templates.");
      setBusy(false);
      return;
    }
    setBusy(false);

    append({
      id: newId(),
      role: "assistant",
      kind: "export-setup",
      runId: latestRunId,
      cpmVersionId: latestConfirmedVersion.versionId,
      format,
      templates,
      submitted: false,
      at: new Date().toISOString(),
    });
  }

  /** Polls GET /exports/{id} to a terminal state (no SSE stream exists for
   * exports, unlike runs) and posts the finished card. */
  function trackExport(exportId: string, narrationId: string) {
    let cancelled = false;
    activeStream.current = () => {
      cancelled = true;
    };

    async function tick() {
      if (cancelled) return;
      let result: ExportResult;
      try {
        result = await getExport(exportId);
      } catch (error) {
        reportApiError(narrationId, error, "Something went wrong checking that export.");
        activeStream.current = null;
        setBusy(false);
        return;
      }
      if (cancelled) return;

      if (result.status === "pending" || result.status === "running") {
        updateNarration(narrationId, exportProgressNarration(result.status));
        setTimeout(() => void tick(), EXPORT_POLL_MS);
        return;
      }

      updateNarration(narrationId, exportOutcomeNarration(result));
      append({
        id: newId(),
        role: "assistant",
        kind: "export-ready",
        export: result,
        at: new Date().toISOString(),
      });
      activeStream.current = null;
      setBusy(false);
    }

    void tick();
  }

  /** An export-setup card's Submit — the only path to `POST .../export`
   * (see ExportSetupCard's own docstring: Submit itself is disabled until
   * every required field is filled, so this only ever receives a complete
   * set). A `needs_png` failure surfaces as its own card with the backend's
   * exact guidance and an offer to fix it; the setup card is left usable so
   * the same fields can be resubmitted once that finishes. */
  async function onExportSubmit(messageId: string, templateId: string, fields: Record<string, string>) {
    const message = messages.find((candidate) => candidate.id === messageId);
    if (!message || message.kind !== "export-setup" || message.submitted) return;

    setExportSubmittingId(messageId);
    setBusy(true);

    let result: ExportResult;
    try {
      result = await requestExport(message.runId, { format: message.format, templateId, fields });
    } catch (error) {
      setExportSubmittingId(null);
      setBusy(false);
      if (error instanceof ApiError && error.code === "needs_png") {
        append({
          id: newId(),
          role: "assistant",
          kind: "needs-png",
          message: error.message,
          cpmVersionId: message.cpmVersionId,
          at: new Date().toISOString(),
        });
        return;
      }
      reportApiError(null, error, "Something went wrong starting that export.");
      return;
    }

    setMessages((current) =>
      current.map((candidate) =>
        candidate.id === messageId && candidate.kind === "export-setup"
          ? { ...candidate, submitted: true }
          : candidate,
      ),
    );
    setExportSubmittingId(null);

    const narrationId = newId();
    append({
      id: narrationId,
      role: "assistant",
      kind: "narration",
      source: exportProgressNarration(result.status),
      at: new Date().toISOString(),
    });
    trackExport(result.exportId, narrationId);
  }

  async function onConfirmProject(messageId: string, review: Review) {
    setConfirmingId(messageId);
    try {
      const result = await confirmReview(projectId);
      const version: ConfirmedVersion = { versionId: result.versionId, version: result.version };
      setMessages((current) =>
        current.map((message) =>
          message.id === messageId && message.kind === "review-summary"
            ? { ...message, confirmedVersion: version }
            : message,
        ),
      );
      setLatestConfirmedVersion(version);
      append({
        id: newId(),
        role: "assistant",
        kind: "narration",
        source: `Confirmed “${review.projectName}” as version ${version.version} (${version.versionId}). Drawing the diagrams next.`,
        at: new Date().toISOString(),
      });
      await runDiagramGeneration(version.versionId);
    } catch (error) {
      if (error instanceof ReviewRefused) {
        append({
          id: newId(),
          role: "assistant",
          kind: "narration",
          source: error.message,
          at: new Date().toISOString(),
        });
      } else {
        // A 401 surfaces here as a plain ApiError, not ReviewRefused — see
        // review.ts's asReview docstring for why that distinction matters.
        reportApiError(null, error, "Something went wrong confirming that.");
      }
    } finally {
      setConfirmingId(null);
    }
  }

  async function onSend(text: string) {
    // The user sees exactly what they typed; only the message sent to the
    // parser is enriched with the pending question and its own context.
    append({ id: newId(), role: "user", kind: "text", text, at: new Date().toISOString() });

    if (pendingExtractionRetry) {
      const { extractionId } = pendingExtractionRetry;
      setPendingExtractionRetry(null);
      void onContinueExtraction(extractionId, text);
      return;
    }

    if (awaitingExportFormat) {
      const format = parseExportFormat(text);
      setAwaitingExportFormat(false);
      if (format) {
        void beginExport(format);
        return;
      }
      // No format recognised in the reply — fall through to the checks
      // below rather than re-asking forever on a message that has moved on.
    }

    if (looksLikeGenerateRequest(text)) {
      if (!latestConfirmedVersion) {
        append({
          id: newId(),
          role: "assistant",
          kind: "narration",
          source: "Nothing's confirmed yet — hit Confirm on the model above first.",
          at: new Date().toISOString(),
        });
        return;
      }
      void runDiagramGeneration(latestConfirmedVersion.versionId);
      return;
    }

    const regenerateRequest = looksLikeRegenerateRequest(text);
    if (regenerateRequest) {
      void onRegenerateDiagram(regenerateRequest.diagramType);
      return;
    }

    if (looksLikeHistoryRequest(text)) {
      void onShowHistory();
      return;
    }

    const exportRequest = looksLikeExportRequest(text);
    if (exportRequest) {
      if (exportRequest.format) {
        void beginExport(exportRequest.format);
      } else {
        setAwaitingExportFormat(true);
        append({
          id: newId(),
          role: "assistant",
          kind: "narration",
          source: "PDF or DOCX?",
          at: new Date().toISOString(),
        });
      }
      return;
    }

    const messageToSend = pendingClarification
      ? `${pendingClarification.contextText}\n\nYou asked: "${pendingClarification.question}"\nMy answer: ${text}`
      : text;

    const narrationId = newId();
    append({
      id: narrationId,
      role: "assistant",
      kind: "narration",
      source: chatEditProgressNarration("pending"),
      at: new Date().toISOString(),
    });

    setBusy(true);

    let edit: ChatEdit;
    try {
      edit = await sendChatMessage(projectId, messageToSend);
    } catch (error) {
      reportApiError(narrationId, error, "Something went wrong sending that.");
      setBusy(false);
      return;
    }

    updateNarration(narrationId, chatEditProgressNarration(edit.status));

    activeStream.current = streamChatEdit(projectId, edit.editId, (snapshot) => {
      if (snapshot.status === "pending" || snapshot.status === "running") {
        updateNarration(narrationId, chatEditProgressNarration(snapshot.status));
        return;
      }

      updateNarration(narrationId, chatEditOutcomeNarration(snapshot));
      activeStream.current = null;
      setBusy(false);

      setPendingClarification(
        snapshot.outcome === "clarify"
          ? { contextText: messageToSend, question: snapshot.clarifyQuestion ?? "" }
          : null,
      );

      if (snapshot.outcome === "applied") {
        void postReviewCard();
      }
    });
  }

  /** Tracks an extraction (fresh attach, or a retry) over SSE (C-4) and
   * decides what happens after it lands. On "extracted", the usual review
   * card. On FR-5's "insufficient" outcome, the conversation stays open
   * instead of dead-ending: `pendingExtractionRetry` names this attempt so
   * `onSend` reads the next message as more detail rather than an edit
   * request, and the canonical reason/guidance (extractionOutcomeNarration —
   * verbatim, see its own docstring) gets exactly one UI-owned sentence
   * appended inviting that reply, never rewording the guidance itself. */
  function trackExtraction(extraction: Extraction, narrationId: string) {
    updateNarration(narrationId, extractionProgressNarration(extraction.status));

    activeStream.current = streamExtraction(projectId, extraction.extractionId, (snapshot) => {
      if (snapshot.status === "pending" || snapshot.status === "running") {
        updateNarration(narrationId, extractionProgressNarration(snapshot.status));
        return;
      }

      activeStream.current = null;
      setBusy(false);

      if (snapshot.status === "succeeded" && snapshot.outcome === "insufficient") {
        setPendingExtractionRetry({ extractionId: snapshot.extractionId });
        updateNarration(
          narrationId,
          `${extractionOutcomeNarration(snapshot)}\n\nReply here with that detail and I'll try ` +
            `again with what you already gave me.`,
        );
        return;
      }

      updateNarration(narrationId, extractionOutcomeNarration(snapshot));
      if (snapshot.status === "succeeded" && snapshot.outcome === "extracted") {
        setPendingExtractionRetry(null);
        void postReviewCard();
      }
    });
  }

  async function onAttach(attachment: Attachment) {
    setPendingClarification(null); // starting a new project supersedes any open question
    setPendingExtractionRetry(null); // ...and any open request for more detail on a stale attempt

    const label =
      attachment.kind === "pdf" ? `Attached ${attachment.file.name}` : "Attached a pasted description";
    append({
      id: newId(),
      role: "user",
      kind: "attachment",
      attachmentKind: attachment.kind,
      label,
      at: new Date().toISOString(),
    });

    const narrationId = newId();
    append({
      id: narrationId,
      role: "assistant",
      kind: "narration",
      source: extractionProgressNarration("pending"),
      at: new Date().toISOString(),
    });

    setBusy(true);

    let extraction: Extraction;
    try {
      extraction =
        attachment.kind === "pdf"
          ? await extractFromPdf(
              projectId,
              attachment.file,
              attachment.projectName || pdfProjectName(attachment.file),
            )
          : await extractFromText(projectId, attachment.text, "New project");
    } catch (error) {
      reportApiError(narrationId, error, "Something went wrong sending that.");
      setBusy(false);
      return;
    }

    trackExtraction(extraction, narrationId);
  }

  /** A reply to an FR-5 "insufficient input" outcome. `POST .../extract`'s
   * `previousExtractionId` combines this text with whatever that attempt
   * already had server-side (see lib/extraction.ts's continueExtraction) —
   * still one model call, just fed a fuller description than before. */
  async function onContinueExtraction(previousExtractionId: string, text: string) {
    const narrationId = newId();
    append({
      id: narrationId,
      role: "assistant",
      kind: "narration",
      source: extractionProgressNarration("pending"),
      at: new Date().toISOString(),
    });

    setBusy(true);

    let extraction: Extraction;
    try {
      extraction = await continueExtraction(projectId, previousExtractionId, text);
    } catch (error) {
      reportApiError(narrationId, error, "Something went wrong sending that.");
      setBusy(false);
      return;
    }

    trackExtraction(extraction, narrationId);
  }

  return (
    <main className="mx-auto flex h-full max-w-2xl flex-col">
      {latestConfirmedVersion ? (
        <div className="border-b border-border bg-muted/40 px-4 py-1.5 text-center text-xs text-muted-foreground">
          Latest confirmed version: v{latestConfirmedVersion.version} ({latestConfirmedVersion.versionId})
        </div>
      ) : null}
      <div className="min-h-0 flex-1 overflow-hidden">
        <MessageList
          messages={messages}
          onConfirm={onConfirmProject}
          confirmingId={confirmingId}
          onExportSubmit={onExportSubmit}
          exportSubmittingId={exportSubmittingId}
          onRenderPng={(cpmVersionId) => void runDiagramGeneration(cpmVersionId, "png")}
          busy={busy}
        />
      </div>
      <Composer onSend={onSend} onAttach={onAttach} busy={busy} />
    </main>
  );
}
