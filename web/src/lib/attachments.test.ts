import { describe, expect, it } from "vitest";

import { classifyAttachment, MAX_PDF_BYTES } from "./attachments";

function file(name: string, type: string, size: number): File {
  const bytes = size > 0 ? new Uint8Array(size) : new Uint8Array();
  return new File([bytes], name, { type });
}

describe("classifyAttachment: accepted", () => {
  it("accepts a PDF by content type", () => {
    const result = classifyAttachment(file("description.pdf", "application/pdf", 1024));
    expect(result).toEqual({ ok: true, kind: "pdf" });
  });

  it("accepts a PDF by extension when the browser reports no type", () => {
    const result = classifyAttachment(file("description.pdf", "", 1024));
    expect(result).toEqual({ ok: true, kind: "pdf" });
  });

  it("accepts a plain text file", () => {
    const result = classifyAttachment(file("notes.txt", "text/plain", 512));
    expect(result).toEqual({ ok: true, kind: "text" });
  });

  it("accepts markdown as text", () => {
    const result = classifyAttachment(file("notes.md", "text/markdown", 512));
    expect(result).toEqual({ ok: true, kind: "text" });
  });
});

describe("classifyAttachment: refused with a specific reason", () => {
  it("refuses a file that is neither PDF nor text", () => {
    const result = classifyAttachment(file("diagram.png", "image/png", 1024));
    expect(result.ok).toBe(false);
    expect(!result.ok && result.reason).toMatch(/diagram\.png.*isn't a PDF or a plain text file/);
  });

  it("refuses an oversized PDF, naming the actual size and the limit", () => {
    const result = classifyAttachment(file("big.pdf", "application/pdf", MAX_PDF_BYTES + 1024));
    expect(result.ok).toBe(false);
    expect(!result.ok && result.reason).toContain("15MB");
    expect(!result.ok && result.reason).toContain("15.0MB");
  });

  it("refuses an empty PDF", () => {
    const result = classifyAttachment(file("empty.pdf", "application/pdf", 0));
    expect(result).toEqual({ ok: false, reason: "That PDF is empty." });
  });

  it("refuses an empty text file", () => {
    const result = classifyAttachment(file("empty.txt", "text/plain", 0));
    expect(result).toEqual({ ok: false, reason: "That file is empty." });
  });

  it("accepts a PDF exactly at the limit", () => {
    const result = classifyAttachment(file("exact.pdf", "application/pdf", MAX_PDF_BYTES));
    expect(result).toEqual({ ok: true, kind: "pdf" });
  });
});
