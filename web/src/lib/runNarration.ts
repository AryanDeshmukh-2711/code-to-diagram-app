/**
 * Turning one Run snapshot into a sentence — the diagram-generation sibling
 * of narration.ts and chatEditNarration.ts, held to the same rule: report
 * what GET .../runs/{id} actually says, never re-derive or soften it.
 *
 * The DoD this exists for: "7 of 8 diagrams ready; entity_relationship
 * failed: <error>" — a partial failure stays a partial failure all the way
 * into the chat bubble. Nothing here collapses a mixed result into "Done!"
 * or drops the failed ones once at least one diagram succeeded (the Watch
 * For this step names explicitly). A skipped diagram — FR-11's honest
 * "nothing here to draw", not an error — is counted and named separately
 * from a failed one, never folded into the same bucket.
 */

import type { Artefact, Run } from "@/lib/runs";

function byStatus(run: Run, status: string): Artefact[] {
  return run.artefacts.filter((artefact) => artefact.status === status);
}

export function runProgressNarration(run: Run): string {
  if (run.status === "pending") {
    return "Queued — I'll start drawing in just a moment.";
  }
  if (run.status === "running") {
    const done = byStatus(run, "succeeded").length + byStatus(run, "failed").length;
    const total = run.artefacts.length || run.requestedTypes.length;
    return done > 0
      ? `Drawing the diagrams — ${done} of ${total} done so far…`
      : "Drawing the diagrams now…";
  }
  return `Status: ${run.status}`;
}

export function runOutcomeNarration(run: Run): string {
  if (run.status === "failed" && run.artefacts.length === 0) {
    return `The run failed before any diagrams could be drawn: ${run.error ?? "an unexpected error happened."}`;
  }

  const total = run.artefacts.length;
  const succeeded = byStatus(run, "succeeded");
  const failed = byStatus(run, "failed");
  const skipped = byStatus(run, "skipped");

  const parts = [`${succeeded.length} of ${total} diagram${total === 1 ? "" : "s"} ready`];

  if (failed.length > 0) {
    parts.push(
      failed
        .map((artefact) => `${artefact.diagramType} failed: ${artefact.error ?? "unknown error"}`)
        .join("; "),
    );
  }

  if (skipped.length > 0) {
    const names = skipped.map((artefact) => artefact.diagramType).join(", ");
    parts.push(`${skipped.length} skipped (${names} — nothing in the model to draw)`);
  }

  return `${parts.join("; ")}.`;
}
