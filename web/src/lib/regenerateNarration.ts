/**
 * Turning one RegenerateResult into a sentence.
 *
 * The DoD this exists for is narrow and absolute: when the plan says nothing
 * changed, `reason` is shown exactly as the backend wrote it — no paraphrase,
 * no "Nothing to redraw!" standing in for it, and critically, nothing is
 * narrated *before* this arrives. POST .../regenerate answers a no-op
 * synchronously (deciding costs one mapper call, not a render), so there is
 * no moment where a "regenerating…" message could honestly appear ahead of
 * knowing the answer — showing one anyway is exactly the fake spinner this
 * step's Watch For names.
 */

import type { RegenerateResult } from "@/lib/runs";

export function regeneratePlanNarration(result: RegenerateResult): string {
  if (!result.changed) {
    return result.reason;
  }

  const stale =
    result.staleTypes.length > 0
      ? ` This will leave ${result.staleTypes.join(", ")} stale relative to it.`
      : "";
  return `Redrawing the ${result.diagramType} diagram — ${result.reason}.${stale}`;
}
