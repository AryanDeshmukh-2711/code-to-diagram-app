/**
 * Deciding what a dropped or picked file is allowed to become — before it
 * ever reaches a network call. This is a fast, client-side courtesy: the
 * server (`extraction/pdf_text.py`) is the real gate on size, and re-checks
 * everything here regardless. What matters for this module is that a bad
 * file gets a specific reason immediately, at the point of attachment,
 * rather than a generic upload failure after a round trip.
 */

export const MAX_PDF_BYTES = 15 * 1024 * 1024;
/** Mirrors extraction/pdf_text.py's MAX_PDF_BYTES. Not the enforcement — the
 * server still checks — just how quickly a user finds out. */

export type AttachmentKind = "pdf" | "text";

export type AttachmentValidation =
  | { ok: true; kind: AttachmentKind }
  | { ok: false; reason: string };

function looksLikePdf(file: File): boolean {
  return file.type === "application/pdf" || file.name.toLowerCase().endsWith(".pdf");
}

function looksLikeText(file: File): boolean {
  if (file.type === "text/plain" || file.type === "text/markdown") return true;
  const name = file.name.toLowerCase();
  return name.endsWith(".txt") || name.endsWith(".md");
}

/** Classifies one dropped or picked file into what it is allowed to become —
 * a PDF upload, or a plain-text description read client-side — or refuses it
 * with the specific reason a user would need to fix it. */
export function classifyAttachment(file: File): AttachmentValidation {
  if (looksLikePdf(file)) {
    if (file.size === 0) {
      return { ok: false, reason: "That PDF is empty." };
    }
    if (file.size > MAX_PDF_BYTES) {
      const mb = (file.size / 1_048_576).toFixed(1);
      return {
        ok: false,
        reason: `That PDF is ${mb}MB; the limit is ${MAX_PDF_BYTES / 1_048_576}MB. Split it or paste the description as text instead.`,
      };
    }
    return { ok: true, kind: "pdf" };
  }

  if (looksLikeText(file)) {
    if (file.size === 0) {
      return { ok: false, reason: "That file is empty." };
    }
    return { ok: true, kind: "text" };
  }

  return {
    ok: false,
    reason: `${file.name || "That file"} isn't a PDF or a plain text file — drop a .pdf or .txt, or paste your description directly.`,
  };
}
