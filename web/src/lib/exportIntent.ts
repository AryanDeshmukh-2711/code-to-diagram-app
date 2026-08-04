/**
 * Recognising "export this as a PDF" / "download the SRS" — the export
 * sibling of generateIntent.ts and regenerateIntent.ts: a small, local,
 * deterministic check performed before the message ever reaches the chat
 * edit-intent parser, never a fifteenth op added to that parser's vocabulary
 * (C-3).
 *
 * Format is optional here on purpose — "export the document" names no
 * format, and the DoD is to ask for it conversationally rather than assume
 * one. `parseExportFormat` is exported separately so the same recognition
 * can be reused on the reply to that question, which rarely repeats an
 * export verb ("PDF, please" has no "export" in it).
 */

const EXPORT_VERB = /\b(export|download|generate|produce|give me|send me|deliver)\b/i;
const DOCUMENT_WORD = /\b(document|doc|srs|report|deliverable|write[- ]?up|pdf|docx|word)\b/i;

const FORMAT_ALIASES: [RegExp, "pdf" | "docx"][] = [
  [/\bdocx\b|\bword\b/i, "docx"],
  [/\bpdf\b/i, "pdf"],
];

export type ExportRequest = { format: "pdf" | "docx" | null };

/** Returns an export request (with whichever format, if any, was named), or
 * null if this message does not read as one at all. */
export function looksLikeExportRequest(text: string): ExportRequest | null {
  if (!EXPORT_VERB.test(text) || !DOCUMENT_WORD.test(text)) return null;
  return { format: parseExportFormat(text) };
}

/** The format named in a piece of text, or null if none was. Used both
 * inside `looksLikeExportRequest` and, on its own, to read a reply to "PDF
 * or DOCX?" that names no export verb at all. */
export function parseExportFormat(text: string): "pdf" | "docx" | null {
  for (const [pattern, format] of FORMAT_ALIASES) {
    if (pattern.test(text)) return format;
  }
  return null;
}
