/**
 * Turning GET .../runs/{id}/history's lineage list into a conversational
 * answer to "what have I changed?" — oldest first, exactly the order the
 * backend already returns it in (regenerate.py's lineage() walks parent_run_id
 * back to the root and reverses once), so nothing here re-sorts or
 * re-derives what happened.
 */

import type { LineageEntry } from "@/lib/runs";

function describeStep(entry: LineageEntry, index: number): string {
  const what =
    entry.kind === "full"
      ? `generated the full set (${entry.regenerated.join(", ")})`
      : `regenerated ${entry.regenerated.join(", ")}`;
  const when = entry.completedAt ?? entry.createdAt;
  const whenSuffix = when ? ` — ${when}` : "";
  return `${index + 1}. ${what}, ${entry.status}${whenSuffix}`;
}

export function historyNarration(entries: LineageEntry[]): string {
  if (entries.length === 0) {
    return "Nothing has been generated for this project yet.";
  }
  return entries.map(describeStep).join("\n");
}
