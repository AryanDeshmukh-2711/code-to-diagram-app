/**
 * Turning one ChatEditRow snapshot into a sentence — the chat-edit sibling
 * of narration.ts, and held to the same rule: this module reports what the
 * row actually says, never a second interpretive pass over it.
 *
 * Two DoD properties live here specifically. An applied edit's confirmation
 * always names the backend's own `summary` and the real `referencesUpdated`
 * count — "invisible mutation is worse in chat than in a form" is the reason
 * there is no branch here that can produce a bare "Done!". And a rejected
 * edit surfaces `reason` completely unprefixed, exactly as review.ts's
 * ReviewRefused shows a form submission's 409 — the same message, because it
 * is the same ReviewError, raised by the same apply_edit_op (C-3).
 */

import type { ChatEdit } from "@/lib/chat";

export function chatEditProgressNarration(status: string): string {
  switch (status) {
    case "pending":
      return "Queued — I'll take a look in just a moment.";
    case "running":
      return "Thinking about that…";
    default:
      return `Status: ${status}`;
  }
}

function pluralize(count: number, noun: string): string {
  return `${count} ${noun}${count === 1 ? "" : "s"}`;
}

export function chatEditOutcomeNarration(edit: ChatEdit): string {
  if (edit.status === "failed") {
    return `That didn't work: ${edit.error ?? "an unexpected error happened."}`;
  }

  if (edit.outcome === "not_edit") {
    return "That didn't read like a request to change the model, so I left it alone.";
  }

  if (edit.outcome === "clarify") {
    return edit.clarifyQuestion ?? "Could you say a bit more about what you mean?";
  }

  if (edit.outcome === "rejected") {
    // The same ReviewError message a 409 from POST .../review/edit would
    // carry — shown bare, the same way the review screen shows a refusal.
    return edit.reason ?? "That edit didn't go through.";
  }

  if (edit.outcome === "applied") {
    const summary = edit.summary ?? "That change was applied";
    const refs = edit.referencesUpdated ?? 0;
    return `${summary}. Updated ${pluralize(refs, "reference")}.`;
  }

  return `Finished with an outcome I don't recognise: ${edit.outcome ?? "none"}.`;
}
