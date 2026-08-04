import type { NarrationSource } from "@/components/chat/StreamingText";
import type { ExportResult, TemplateSummary } from "@/lib/exports";
import type { QuotaRefusal } from "@/lib/quota";
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
  | ExportSetupMessage
  | NeedsPngMessage
  | ExportReadyMessage
  | QuotaRefusalMessage
  | SessionExpiredMessage;

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

/** What POST .../review/confirm returns. Named here once so the card, the
 * message type, and the session's "last confirmed version" all mean the
 * same shape. */
export type ConfirmedVersion = {
  versionId: string;
  version: number;
};

export type ReviewSummaryMessage = BaseMessage & {
  role: "assistant";
  kind: "review-summary";
  review: Review;
  /** Set once this exact card has been confirmed. Confirming is a button
   * click on one specific card, never something chat text can trigger
   * (FR-6/FR-7) — see Composer/ChatSession, which have no path from a typed
   * message to this field. */
  confirmedVersion?: ConfirmedVersion | null;
};

export type DiagramProgressMessage = BaseMessage & {
  role: "assistant";
  kind: "diagram-progress";
  run: Run;
};

/** Format is already known by the time this renders — collected
 * conversationally before the card ever appears. What is left to collect is
 * the template (skipped as a choice when the tier allows only one) and that
 * template's own required fields (FR-15). Submit never fires
 * `POST .../export` until every one of them is filled — see
 * ExportSetupCard's own docstring. */
export type ExportSetupMessage = BaseMessage & {
  role: "assistant";
  kind: "export-setup";
  runId: string;
  cpmVersionId: string;
  format: "pdf" | "docx";
  templates: TemplateSummary[];
  /** Set once this card's Submit has fired, so a stale card cannot start a
   * second export after the flow has moved on. */
  submitted: boolean;
};

/** DOCX requested for a run only ever rendered as SVG. `message` is the
 * API's own `needs_png` guidance, shown verbatim — see exportNarration.ts's
 * docstring for why this module writes none of its own copy for it. */
export type NeedsPngMessage = BaseMessage & {
  role: "assistant";
  kind: "needs-png";
  message: string;
  cpmVersionId: string;
};

export type ExportReadyMessage = BaseMessage & {
  role: "assistant";
  kind: "export-ready";
  export: ExportResult;
};

/** A 402. `refusal` is `billing/quota.py`'s own `QuotaRefusal` — no rule ID
 * attaches to this step, but see lib/quota.ts's docstring for the principle
 * that does. */
export type QuotaRefusalMessage = BaseMessage & {
  role: "assistant";
  kind: "quota-refusal";
  refusal: QuotaRefusal;
};

/** A 401. Never text glued into a narration bubble — see
 * SessionExpiredCard's own docstring for why the transcript above this stays
 * intact rather than the app silently navigating away. */
export type SessionExpiredMessage = BaseMessage & {
  role: "assistant";
  kind: "session-expired";
  returnTo: string;
};
