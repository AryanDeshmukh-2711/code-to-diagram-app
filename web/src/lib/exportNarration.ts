/**
 * Turning one ExportResult into a sentence — the export sibling of
 * runNarration.ts, held to the same rule: report what the backend actually
 * says, never soften or re-derive it.
 *
 * A structured failure (`needs_png`, `missing_fields`) is not narrated by
 * this module at all: ChatSession reads `ApiError.message` directly for
 * those, because the DoD is that the API's own guidance reaches the user
 * verbatim, and adding a second sentence in front of it here would be
 * exactly that "own copy" the Watch For names.
 */

import type { ExportResult } from "@/lib/exports";

export function exportProgressNarration(status: string): string {
  if (status === "pending") return "Queued — I'll start assembling the document in a moment.";
  if (status === "running") return "Assembling the document…";
  return `Status: ${status}`;
}

export function exportOutcomeNarration(result: ExportResult): string {
  if (result.status === "failed") {
    return `The export failed: ${result.error ?? "an unexpected error happened."}`;
  }
  if (result.status === "succeeded") {
    return `Your ${result.format.toUpperCase()} is ready.`;
  }
  return `Status: ${result.status}`;
}
