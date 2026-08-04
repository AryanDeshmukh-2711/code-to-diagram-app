"use client";

import { useEffect, useRef, useState } from "react";

import type { Attachment } from "@/components/chat/Composer";
import { Composer } from "@/components/chat/Composer";
import { MessageList } from "@/components/chat/MessageList";
import type { ChatMessage, ConfirmedVersion } from "@/components/chat/types";
import { type ChatEdit, sendChatMessage, streamChatEdit } from "@/lib/chat";
import { chatEditOutcomeNarration, chatEditProgressNarration } from "@/lib/chatEditNarration";
import { ApiError } from "@/lib/client";
import { extractFromPdf, extractFromText, streamExtraction, type Extraction } from "@/lib/extraction";
import { looksLikeGenerateRequest } from "@/lib/generateIntent";
import { extractionOutcomeNarration, extractionProgressNarration } from "@/lib/narration";
import { confirmReview, loadReview, type Review, ReviewRefused } from "@/lib/review";
import { runOutcomeNarration, runProgressNarration } from "@/lib/runNarration";
import { type Run, startRun, streamRun } from "@/lib/runs";

function newId(): string {
  return typeof crypto !== "undefined" && crypto.randomUUID
    ? crypto.randomUUID()
    : `m_${Date.now()}_${Math.random().toString(36).slice(2)}`;
}

function pdfProjectName(file: File): string {
  return file.name.replace(/\.pdf$/i, "").trim() || "New project";
}

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
 * parsing (P-M6-2), the confirm gate (P-M6-7), and diagram generation
 * (P-M6-8).
 *
 * Everything narrated here comes straight off the row the backend returns
 * for whichever job is in flight: lib/narration.ts, lib/chatEditNarration.ts
 * and lib/runNarration.ts are the only things that turn a row into a
 * sentence, and none of them invent detail the row does not carry (FR-9,
 * C-3, FR-10/11/12/20). A partial run failure names exactly which diagram
 * failed and why, with every other diagram still counted ready — there is no
 * path here that collapses that into "Done!".
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
 * "Generate the diagrams" is recognised the same deliberate way "attach" is
 * (P-M6-4): a small local check (lib/generateIntent.ts) before a message
 * ever reaches the edit-intent parser, never a fifteenth op added to that
 * parser's vocabulary.
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
  const activeStream = useRef<(() => void) | null>(null);

  useEffect(() => {
    return () => activeStream.current?.();
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

  /** POST /runs, and a live diagram-progress card fed by the same SSE
   * mechanism run progress has always streamed through (C-4). Called both
   * right after a successful confirm and from a "generate the diagrams"
   * follow-up — the same action, two ways to reach it. */
  async function runDiagramGeneration(cpmVersionId: string) {
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
      run = await startRun({ projectId, cpmVersionId });
    } catch (error) {
      updateNarration(
        narrationId,
        error instanceof ApiError ? error.message : "Something went wrong starting that.",
      );
      setBusy(false);
      return;
    }

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
      append({
        id: newId(),
        role: "assistant",
        kind: "narration",
        source:
          error instanceof ReviewRefused ? error.message : "Something went wrong confirming that.",
        at: new Date().toISOString(),
      });
    } finally {
      setConfirmingId(null);
    }
  }

  async function onSend(text: string) {
    // The user sees exactly what they typed; only the message sent to the
    // parser is enriched with the pending question and its own context.
    append({ id: newId(), role: "user", kind: "text", text, at: new Date().toISOString() });

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
      updateNarration(
        narrationId,
        error instanceof ApiError ? error.message : "Something went wrong sending that.",
      );
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

  async function onAttach(attachment: Attachment) {
    setPendingClarification(null); // starting a new project supersedes any open question

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
          ? await extractFromPdf(projectId, attachment.file, pdfProjectName(attachment.file))
          : await extractFromText(projectId, attachment.text, "New project");
    } catch (error) {
      updateNarration(
        narrationId,
        error instanceof ApiError ? error.message : "Something went wrong sending that.",
      );
      setBusy(false);
      return;
    }

    updateNarration(narrationId, extractionProgressNarration(extraction.status));

    activeStream.current = streamExtraction(projectId, extraction.extractionId, (snapshot) => {
      if (snapshot.status === "pending" || snapshot.status === "running") {
        updateNarration(narrationId, extractionProgressNarration(snapshot.status));
        return;
      }

      updateNarration(narrationId, extractionOutcomeNarration(snapshot));
      activeStream.current = null;
      setBusy(false);

      if (snapshot.status === "succeeded" && snapshot.outcome === "extracted") {
        void postReviewCard();
      }
    });
  }

  return (
    <main className="mx-auto flex h-screen max-w-2xl flex-col">
      {latestConfirmedVersion ? (
        <div className="border-b border-border bg-muted/40 px-4 py-1.5 text-center text-xs text-muted-foreground">
          Latest confirmed version: v{latestConfirmedVersion.version} ({latestConfirmedVersion.versionId})
        </div>
      ) : null}
      <div className="flex-1 overflow-hidden">
        <MessageList messages={messages} onConfirm={onConfirmProject} confirmingId={confirmingId} />
      </div>
      <Composer onSend={onSend} onAttach={onAttach} busy={busy} />
    </main>
  );
}
