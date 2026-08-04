"use client";

import { useEffect, useRef, useState } from "react";

import type { Attachment } from "@/components/chat/Composer";
import { Composer } from "@/components/chat/Composer";
import { MessageList } from "@/components/chat/MessageList";
import type { ChatMessage } from "@/components/chat/types";
import { ApiError } from "@/lib/client";
import { extractFromPdf, extractFromText, streamExtraction, type Extraction } from "@/lib/extraction";
import { extractionOutcomeNarration, extractionProgressNarration } from "@/lib/narration";
import { loadReview } from "@/lib/review";

function newId(): string {
  return typeof crypto !== "undefined" && crypto.randomUUID
    ? crypto.randomUUID()
    : `m_${Date.now()}_${Math.random().toString(36).slice(2)}`;
}

function pdfProjectName(file: File): string {
  return file.name.replace(/\.pdf$/i, "").trim() || "New project";
}

/**
 * Wires the composer to real extraction (P-M6-1). Everything this component
 * narrates comes straight off the ExtractionRow the backend returns —
 * lib/narration.ts is the only thing that turns that row into a sentence,
 * and it never invents detail the row does not carry (FR-9, Watch For).
 *
 * Editing through chat is not wired here — that is P-M6-2's job to connect,
 * in a later step. `onSend` says so rather than pretending to act on it.
 */
export function ChatSession({ projectId }: { projectId: string }) {
  const [messages, setMessages] = useState<ChatMessage[]>(() => [
    {
      id: newId(),
      role: "assistant",
      kind: "narration",
      source:
        "Drop a PDF or paste a description to get started — I'll turn it into a model you can review.",
      at: new Date().toISOString(),
    },
  ]);
  const [busy, setBusy] = useState(false);
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

  function onSend(text: string) {
    append({ id: newId(), role: "user", kind: "text", text, at: new Date().toISOString() });
    append({
      id: newId(),
      role: "assistant",
      kind: "narration",
      source:
        "Editing through chat isn't wired up yet — that lands in a later step. Use the review screen for now.",
      at: new Date().toISOString(),
    });
  }

  async function onAttach(attachment: Attachment) {
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
        void loadReview(projectId).then((review) => {
          append({
            id: newId(),
            role: "assistant",
            kind: "review-summary",
            review,
            at: new Date().toISOString(),
          });
        });
      }
    });
  }

  return (
    <main className="mx-auto flex h-screen max-w-2xl flex-col">
      <div className="flex-1 overflow-hidden">
        <MessageList messages={messages} />
      </div>
      <Composer onSend={onSend} onAttach={onAttach} busy={busy} />
    </main>
  );
}
