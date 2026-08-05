"use client";

import { useState } from "react";

import type { Attachment } from "@/components/chat/Composer";
import { Composer } from "@/components/chat/Composer";
import { MessageList } from "@/components/chat/MessageList";
import type { ChatMessage } from "@/components/chat/types";
import type { ExportResult } from "@/lib/exports";
import type { Review } from "@/lib/review";
import type { Run } from "@/lib/runs";

/**
 * A sandbox for the chat primitives built in P-M6-4 — no network calls, no
 * real project. Later prompts wire Composer/MessageList to the real
 * extraction, chat and run endpoints; this page exists to prove the
 * components themselves work before anything is wired to them.
 */

const SAMPLE_REVIEW: Review = {
  projectId: "demo",
  projectName: "Library Management System",
  draft: {},
  issues: [],
  confirmable: true,
  counts: { entities: 8, relationships: 9, actors: 3, useCases: 6 },
  lastEdit: "Renamed “Book” to “Publication” — 13 other places were updated to match.",
  referencesUpdated: 13,
};

const SAMPLE_RUN: Run = {
  runId: "run_demo",
  projectId: "demo",
  cpmVersionId: "cpmv_demo",
  status: "running",
  kind: "full",
  parentRunId: null,
  requestedTypes: ["class", "useCase", "sequence", "activity"],
  artefacts: [
    { diagramType: "class", title: "Class diagram", status: "succeeded", engine: "plantuml", error: null, attempts: 1, bytes: 4213, cpmVersionId: "cpmv_demo", originRunId: "run_demo", carriedForward: false },
    { diagramType: "useCase", title: "Use case diagram", status: "succeeded", engine: "plantuml", error: null, attempts: 1, bytes: 2110, cpmVersionId: "cpmv_demo", originRunId: "run_demo", carriedForward: false },
    { diagramType: "sequence", title: "Sequence diagram", status: "running", engine: null, error: null, attempts: 0, bytes: null, cpmVersionId: null, originRunId: null, carriedForward: false },
    { diagramType: "activity", title: "Activity diagram", status: "pending", engine: null, error: null, attempts: 0, bytes: null, cpmVersionId: null, originRunId: null, carriedForward: false },
  ],
  durationMs: null,
  llmCostUsd: "0",
  attempts: 1,
  error: null,
};

const SAMPLE_EXPORT: ExportResult = {
  exportId: "exp_demo",
  status: "succeeded",
  format: "pdf",
  url: "/exports/exp_demo/download?token=demo",
  bytes: 184_320,
  error: null,
};

async function* typewriter(sentence: string): AsyncIterable<string> {
  for (const word of sentence.split(" ")) {
    await new Promise((resolve) => setTimeout(resolve, 60));
    yield (word + " ");
  }
}

let counter = 0;
function nextId(prefix: string): string {
  counter += 1;
  return `${prefix}_${counter}`;
}

const INITIAL_MESSAGES: ChatMessage[] = [
  {
    id: nextId("m"),
    role: "assistant",
    kind: "narration",
    source: "Drop a PDF or paste a description below to get started, or ask me to change something already in review.",
    at: new Date().toISOString(),
  },
  { id: nextId("m"), role: "assistant", kind: "review-summary", review: SAMPLE_REVIEW, at: new Date().toISOString() },
  { id: nextId("m"), role: "assistant", kind: "diagram-progress", run: SAMPLE_RUN, at: new Date().toISOString() },
  { id: nextId("m"), role: "assistant", kind: "export-ready", export: SAMPLE_EXPORT, at: new Date().toISOString() },
];

export default function ChatPrimitivesSandbox() {
  const [messages, setMessages] = useState<ChatMessage[]>(INITIAL_MESSAGES);

  function append(message: ChatMessage) {
    setMessages((current) => [...current, message]);
  }

  function onSend(text: string) {
    append({ id: nextId("m"), role: "user", kind: "text", text, at: new Date().toISOString() });
    append({
      id: nextId("m"),
      role: "assistant",
      kind: "narration",
      source: () => typewriter(`Got it — "${text}". A later step wires this to the real edit-intent parser.`),
      at: new Date().toISOString(),
    });
  }

  function onAttach(attachment: Attachment) {
    const label =
      attachment.kind === "pdf" ? `Attached ${attachment.file.name}` : "Attached a pasted description";
    append({
      id: nextId("m"),
      role: "user",
      kind: "attachment",
      attachmentKind: attachment.kind,
      label,
      at: new Date().toISOString(),
    });
    append({
      id: nextId("m"),
      role: "assistant",
      kind: "narration",
      source: () => typewriter("Reading that now — a later step wires this to the real extraction pipeline."),
      at: new Date().toISOString(),
    });
  }

  return (
    <main className="mx-auto flex h-screen max-w-2xl flex-col">
      <div className="border-b border-border px-4 py-3">
        <h1 className="text-sm font-semibold">Chat primitives sandbox</h1>
        <p className="text-xs text-muted-foreground">
          No network calls here — every card and message below is local state.
        </p>
      </div>
      <div className="flex-1 overflow-hidden">
        <MessageList messages={messages} />
      </div>
      <Composer onSend={onSend} onAttach={onAttach} />
    </main>
  );
}
