/**
 * Turning one ExtractionRow snapshot into a sentence — nothing more.
 *
 * FR-9's boundary for this step: the CPM is the only thing rendering ever
 * depends on, and this module is not part of that pipeline at all. It reads
 * `status`/`outcome`/`reason`/`guidance` off the same row `GET
 * .../extractions/{id}` already returns and reports them; it never re-derives
 * a count, never rewrites `reason` or `guidance`, and never runs a second
 * model pass to make the report sound more finished than the extraction was.
 * An `InsufficientInput` guidance list that got softened on the way to the
 * chat bubble would be exactly the fabrication risk FR-5 exists to prevent,
 * arriving through the narration layer instead of the extractor.
 */

import type { Extraction } from "@/lib/extraction";

/** What to say while a job is still in flight. Never "thinking…" — each
 * status the row can actually be in gets its own sentence, because a
 * placeholder that fits every state is indistinguishable from reporting
 * nothing at all. */
export function extractionProgressNarration(status: string): string {
  switch (status) {
    case "pending":
      return "Queued — I'll start reading it in just a moment.";
    case "running":
      return "Reading through it now…";
    default:
      return `Status: ${status}`;
  }
}

/** What to say once a job has reached a terminal status. `reason` and
 * `guidance` are reproduced verbatim from the row — see the module docstring
 * for why nothing here is allowed to paraphrase them. */
export function extractionOutcomeNarration(extraction: Extraction): string {
  if (extraction.status === "failed") {
    return `That didn't work: ${extraction.error ?? "an unexpected error happened."}`;
  }

  if (extraction.outcome === "insufficient") {
    const guidance = extraction.guidance ?? [];
    return [extraction.reason ?? "", ...guidance.map((line) => `• ${line}`)]
      .filter((line) => line.length > 0)
      .join("\n");
  }

  if (extraction.outcome === "extracted") {
    return "Done — here's what I found.";
  }

  // status is "succeeded" but outcome is neither known value — an honest
  // report of an unexpected shape beats guessing which branch it meant.
  return `Finished with an outcome I don't recognise: ${extraction.outcome ?? "none"}.`;
}
