"use client";

import { useEffect, useRef } from "react";
import { FileText, Paperclip } from "lucide-react";

import type { ChatMessage } from "@/components/chat/types";
import { DiagramProgressCard } from "@/components/chat/cards/DiagramProgressCard";
import { ExportReadyCard } from "@/components/chat/cards/ExportReadyCard";
import { ReviewSummaryCard } from "@/components/chat/cards/ReviewSummaryCard";
import { StreamingText } from "@/components/chat/StreamingText";

export type MessageListProps = {
  messages: ChatMessage[];
};

export function MessageList({ messages }: MessageListProps) {
  const bottomRef = useRef<HTMLDivElement>(null);

  useEffect(() => {
    bottomRef.current?.scrollIntoView({ block: "end" });
  }, [messages.length]);

  return (
    <div className="flex flex-col gap-4 overflow-y-auto p-4" role="log" aria-live="polite">
      {messages.map((message) => (
        <MessageRow key={message.id} message={message} />
      ))}
      <div ref={bottomRef} />
    </div>
  );
}

function MessageRow({ message }: { message: ChatMessage }) {
  const isUser = message.role === "user";
  return (
    <div className={`flex ${isUser ? "justify-end" : "justify-start"}`}>
      <MessageContent message={message} />
    </div>
  );
}

function MessageContent({ message }: { message: ChatMessage }) {
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
      return <ReviewSummaryCard review={message.review} />;

    case "diagram-progress":
      return <DiagramProgressCard run={message.run} />;

    case "export-ready":
      return <ExportReadyCard export={message.export} />;
  }
}
