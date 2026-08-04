/**
 * Recognising "what have I changed?" — the same kind of small, local,
 * deterministic check as generateIntent.ts and regenerateIntent.ts, and for
 * the same reason: this is a request to read GET .../runs/{id}/history, not
 * an edit for P-M6-2's parser to weigh in on.
 */

const HISTORY_PATTERN = /\b(what.*\b(chang|regenerat)|history|change[ -]?log)/i;

export function looksLikeHistoryRequest(text: string): boolean {
  return HISTORY_PATTERN.test(text);
}
