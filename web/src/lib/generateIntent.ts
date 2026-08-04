/**
 * Recognising "generate the diagrams" — deliberately not the chat
 * edit-intent parser's job.
 *
 * P-M6-2's parser vocabulary is the fourteen CPM edit ops and nothing else
 * (see shared/chat/intent.py); adding a fifteenth "generate" op would blur
 * exactly the line C-3 draws around it, the same reason "confirm" is not in
 * that vocabulary either (P-M6-7). Detecting a generate request is instead a
 * small, local, deterministic check performed before a message is ever sent
 * to that parser — no model call, nothing to fabricate.
 */

const GENERATE_PATTERN = /\b(generate|draw|render|make|create|build)\b[\s\S]*\b(diagram|diagrams)\b/i;

export function looksLikeGenerateRequest(text: string): boolean {
  return GENERATE_PATTERN.test(text);
}
