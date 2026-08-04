"use client";

import { useEffect, useRef } from "react";
import { FileText, Paperclip } from "lucide-react";

import type { ChatMessage } from "@/components/chat/types";
import { DiagramProgressCard } from "@/components/chat/cards/DiagramProgressCard";
import { ExportReadyCard } from "@/components/chat/cards/ExportReadyCard";
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
};

export function MessageList({ messages, onConfirm, confirmingId = null }: MessageListProps) {
  const bottomRef = useRef<HTMLDivElement>(null);

  useEffect(() => {
    bottomRef.current?.scrollIntoView({ block: "end" });
  }, [messages.length]);

  return (
    <div className="flex flex-col gap-4 overflow-y-auto p-4" role="log" aria-live="polite">
      {messages.map((message) => (
        <MessageRow key={message.id} message={message} onConfirm={onConfirm} confirmingId={confirmingId} />
      ))}
      <div ref={bottomRef} />
    </div>
  );
}

function MessageRow({
  message,
  onConfirm,
  confirmingId,
}: {
  message: ChatMessage;
  onConfirm?: (messageId: string, review: Review) => void;
  confirmingId: string | null;
}) {
  const isUser = message.role === "user";
  return (
    <div className={`flex ${isUser ? "justify-end" : "justify-start"}`}>
      <MessageContent message={message} onConfirm={onConfirm} confirmingId={confirmingId} />
    </div>
  );
}

function MessageContent({
  message,
  onConfirm,
  confirmingId,
}: {
  message: ChatMessage;
  onConfirm?: (messageId: string, review: Review) => void;
  confirmingId: string | null;
}) {
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

    case "export-ready":
      return <ExportReadyCard export={message.export} />;
  }
}
