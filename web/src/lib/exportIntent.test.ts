import { describe, expect, it } from "vitest";

import { looksLikeExportRequest, parseExportFormat } from "./exportIntent";

describe("looksLikeExportRequest", () => {
  it("recognises an export verb naming a format", () => {
    expect(looksLikeExportRequest("export this as a PDF")).toEqual({ format: "pdf" });
    expect(looksLikeExportRequest("download the docx")).toEqual({ format: "docx" });
    expect(looksLikeExportRequest("give me the word document")).toEqual({ format: "docx" });
  });

  it("recognises an export request naming no format", () => {
    expect(looksLikeExportRequest("export the document")).toEqual({ format: null });
    expect(looksLikeExportRequest("I'd like to download the SRS report")).toEqual({
      format: null,
    });
  });

  it("returns null for a generate-the-diagrams request", () => {
    expect(looksLikeExportRequest("generate the diagrams")).toBeNull();
  });

  it("returns null when there's no document word at all", () => {
    expect(looksLikeExportRequest("export my regards to the team")).toBeNull();
  });

  it("returns null on a plain edit request", () => {
    expect(looksLikeExportRequest("rename Book to Publication")).toBeNull();
  });
});

describe("parseExportFormat", () => {
  it("reads a bare format reply with no export verb", () => {
    expect(parseExportFormat("PDF, please")).toBe("pdf");
    expect(parseExportFormat("docx")).toBe("docx");
    expect(parseExportFormat("Word")).toBe("docx");
  });

  it("returns null when no format is named", () => {
    expect(parseExportFormat("whichever is easiest")).toBeNull();
  });
});
