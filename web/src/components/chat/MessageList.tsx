"use client";

import { useEffect, useRef } from "react";
import { FileText, Paperclip } from "lucide-react";

import type { ChatMessage } from "@/components/chat/types";
import { DiagramProgressCard } from "@/components/chat/cards/DiagramProgressCard";
import { ExportReadyCard } from "@/components/chat/cards/ExportReadyCard";
import { ExportSetupCard } from "@/components/chat/cards/ExportSetupCard";
import { NeedsPngCard } from "@/components/chat/cards/NeedsPngCard";
import { ReviewSummaryCard } from "@/components/chat/cards/ReviewSummaryCard";
import { StreamingText } from "@/components/chat/StreamingText";
import type { Review } from "@/lib/review";

export type MessageListProps = {
  messages: ChatMessage[];
  /** Wired to exactly one control: the confirm button inside a
   * review-summary card. Omit entirely and no message in the list can ever
   * confirm anything — that is how the sandbox stays confirm-free without a
   * separate code path (FR-6/FR-7). */
  onConfirm?: (messageId: string, review: Review) => void;
  confirmingId?: string | null;
  /** Wired to an export-setup card's Submit — the only way `POST
   * .../export` is ever reached (see ExportSetupCard's own docstring for
   * why it cannot fire before every required field is filled). */
  onExportSubmit?: (messageId: string, templateId: string, fields: Record<string, string>) => void;
  exportSubmittingId?: string | null;
  /** Wired to a needs-png card's Render PNG button. */
  onRenderPng?: (cpmVersionId: string) => void;
  busy?: boolean;
};

export function MessageList({
  messages,
  onConfirm,
  confirmingId = null,
  onExportSubmit,
  exportSubmittingId = null,
  onRenderPng,
  busy = false,
}: MessageListProps) {
  const bottomRef = useRef<HTMLDivElement>(null);

  useEffect(() => {
    bottomRef.current?.scrollIntoView({ block: "end" });
  }, [messages.length]);

  return (
    <div className="flex flex-col gap-4 overflow-y-auto p-4" role="log" aria-live="polite">
      {messages.map((message) => (
        <MessageRow
          key={message.id}
          message={message}
          onConfirm={onConfirm}
          confirmingId={confirmingId}
          onExportSubmit={onExportSubmit}
          exportSubmittingId={exportSubmittingId}
          onRenderPng={onRenderPng}
          busy={busy}
        />
      ))}
      <div ref={bottomRef} />
    </div>
  );
}

type RowProps = {
  message: ChatMessage;
  onConfirm?: (messageId: string, review: Review) => void;
  confirmingId: string | null;
  onExportSubmit?: (messageId: string, templateId: string, fields: Record<string, string>) => void;
  exportSubmittingId: string | null;
  onRenderPng?: (cpmVersionId: string) => void;
  busy: boolean;
};

function MessageRow({ message, ...rest }: RowProps) {
  const isUser = message.role === "user";
  return (
    <div className={`flex ${isUser ? "justify-end" : "justify-start"}`}>
      <MessageContent message={message} {...rest} />
    </div>
  );
}

function MessageContent({
  message,
  onConfirm,
  confirmingId,
  onExportSubmit,
  exportSubmittingId,
  onRenderPng,
  busy,
}: RowProps) {
  switch (message.kind) {
    case "text":
      return (
        <div className="max-w-md rounded-2xl bg-primary px-4 py-2.5 text-sm text-primary-foreground">
          {message.text}
        </div>
      );

    case "attachment":
      return (
        <div className="flex max-w-md items-center gap-2 rounded-2xl bg-primary px-4 py-2.5 text-sm text-primary-foreground">
          {message.attachmentKind === "pdf" ? (
            <FileText className="size-4 shrink-0" />
          ) : (
            <Paperclip className="size-4 shrink-0" />
          )}
          <span>{message.label}</span>
        </div>
      );

    case "narration":
      return (
        <div className="max-w-md rounded-2xl bg-muted px-4 py-2.5">
          <StreamingText source={message.source} />
        </div>
      );

    case "review-summary":
      return (
        <ReviewSummaryCard
          review={message.review}
          confirmedVersion={message.confirmedVersion}
          confirming={confirmingId === message.id}
          onConfirm={onConfirm ? () => onConfirm(message.id, message.review) : undefined}
        />
      );

    case "diagram-progress":
      return <DiagramProgressCard run={message.run} />;

    case "export-setup":
      return (
        <ExportSetupCard
          format={message.format}
          templates={message.templates}
          submitting={exportSubmittingId === message.id}
          submitted={message.submitted}
          onSubmit={(templateId, fields) => onExportSubmit?.(message.id, templateId, fields)}
        />
      );

    case "needs-png":
      return (
        <NeedsPngCard
          message={message.message}
          busy={busy}
          onRenderPng={() => onRenderPng?.(message.cpmVersionId)}
        />
      );

    case "export-ready":
      return <ExportReadyCard export={message.export} />;
  }
}
