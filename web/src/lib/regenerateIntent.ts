/**
 * Recognising "redraw the class diagram" — a small, local, deterministic
 * check, the same reason "generate the diagrams" (P-M6-8) never reaches the
 * chat edit-intent parser: this is a workflow action, not a fifteenth op in
 * a vocabulary that is deliberately only the fourteen CPM edits (C-3).
 */

const REGENERATE_VERB = /\b(redraw|regenerate|recreate|redo|refresh)\b/i;

/** Backend diagram-type identifiers (see diagrams/registry.py), matched
 * against the ways someone would actually say them. Order matters only in
 * that a more specific phrase ("use case") must be checked before a bare
 * substring could ever ambiguously apply — none currently overlap. */
const DIAGRAM_TYPE_ALIASES: [RegExp, string][] = [
  [/\buse[ -]?case\b/i, "use_case"],
  [/\bentity[ -]?relationship\b/i, "entity_relationship"],
  [/\bclass\b/i, "class"],
  [/\bsequence\b/i, "sequence"],
  [/\bactivity\b/i, "activity"],
  [/\bstate\b/i, "state"],
  [/\bcomponent\b/i, "component"],
  [/\bdeployment\b/i, "deployment"],
];

export type RegenerateRequest = { diagramType: string };

/** Returns which diagram was named, or null if this message does not read
 * as a regenerate request at all, or names no diagram this product draws.
 * A bare "regenerate the diagrams" (no type) is deliberately not matched
 * here — this step is about one named diagram, not a bulk trigger. */
export function looksLikeRegenerateRequest(text: string): RegenerateRequest | null {
  if (!REGENERATE_VERB.test(text)) return null;
  for (const [pattern, diagramType] of DIAGRAM_TYPE_ALIASES) {
    if (pattern.test(text)) return { diagramType };
  }
  return null;
}
