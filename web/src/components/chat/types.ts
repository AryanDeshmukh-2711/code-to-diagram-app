import type { NarrationSource } from "@/components/chat/StreamingText";
import type { ExportResult } from "@/lib/exports";
import type { Review } from "@/lib/review";
import type { Run } from "@/lib/runs";

/**
 * Everything that can appear in the message stream.
 *
 * A card is a distinct message kind, not a template rendered inside a text
 * bubble — that split is what keeps "review-summary" or "diagram-progress"
 * from ever degrading into freeform HTML glued into a chat message. Adding a
 * new card kind later means adding a new variant here and a new component,
 * never widening a generic bubble's contents.
 */
export type ChatMessage =
  | UserTextMessage
  | UserAttachmentMessage
  | AssistantNarrationMessage
  | ReviewSummaryMessage
  | DiagramProgressMessage
  | ExportReadyMessage;

type BaseMessage = {
  id: string;
  at: string;
};

/** A chat message the user typed — an edit request or a plain question.
 * Never how a project description arrives; that is always an attachment. */
export type UserTextMessage = BaseMessage & {
  role: "user";
  kind: "text";
  text: string;
};

/** The explicit "this is my project" affordance, distinguished at the point
 * of attachment rather than guessed from what the text says. */
export type UserAttachmentMessage = BaseMessage & {
  role: "user";
  kind: "attachment";
  attachmentKind: "pdf" | "text";
  label: string;
};

/** Freeform assistant prose. `source` is a finished string once the backend
 * supports only that, or a factory for a fresh token stream once it can
 * stream them — the message list does not need to know which. */
export type AssistantNarrationMessage = BaseMessage & {
  role: "assistant";
  kind: "narration";
  source: NarrationSource;
};

export type ReviewSummaryMessage = BaseMessage & {
  role: "assistant";
  kind: "review-summary";
  review: Review;
};

export type DiagramProgressMessage = BaseMessage & {
  role: "assistant";
  kind: "diagram-progress";
  run: Run;
};

export type ExportReadyMessage = BaseMessage & {
  role: "assistant";
  kind: "export-ready";
  export: ExportResult;
};
