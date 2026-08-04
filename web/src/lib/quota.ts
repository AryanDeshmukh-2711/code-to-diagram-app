/**
 * Reading a 402 quota refusal straight off the API's own structured detail.
 *
 * No non-negotiable rule ID attaches to this step, but the same "never let
 * an LLM touch canonical data" principle behind FR-3 and FR-10·11·12·20
 * governs it anyway: `code`, `message`, `tier`, `limit`, `used`, `upgradeTo`
 * and `upgradeGives` are `billing/quota.py`'s own `QuotaRefusal.as_dict()`,
 * unchanged. Nothing here reformats `message` or recomputes `limit`/`used`
 * from anything else — the whole point is that this project already tested
 * for the drift a re-paraphrase reintroduces, and refuses to do it again.
 */

import { ApiError } from "@/lib/client";

export type QuotaRefusal = {
  code: string;
  message: string;
  tier: string;
  limit: string | number | null;
  used: string | number | null;
  upgradeTo: string | null;
  upgradeGives: string;
};

/** Returns the refusal for a 402 `ApiError`, or null for anything else —
 * including a 402 whose detail does not have this shape, which is treated
 * as "not a quota refusal" rather than guessed at. */
export function quotaRefusal(error: unknown): QuotaRefusal | null {
  if (!(error instanceof ApiError) || error.status !== 402) return null;

  const detail = error.detail;
  if (!detail || typeof detail !== "object") return null;
  const d = detail as Record<string, unknown>;

  if (typeof d.code !== "string" || typeof d.message !== "string" || typeof d.tier !== "string") {
    return null;
  }

  const limit = d.limit;
  const used = d.used;
  return {
    code: d.code,
    message: d.message,
    tier: d.tier,
    limit: typeof limit === "string" || typeof limit === "number" ? limit : null,
    used: typeof used === "string" || typeof used === "number" ? used : null,
    upgradeTo: typeof d.upgradeTo === "string" ? d.upgradeTo : null,
    upgradeGives: typeof d.upgradeGives === "string" ? d.upgradeGives : "",
  };
}
