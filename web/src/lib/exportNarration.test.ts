import { describe, expect, it } from "vitest";

import { exportOutcomeNarration, exportProgressNarration } from "./exportNarration";
import type { ExportResult } from "./exports";

function result(overrides: Partial<ExportResult> = {}): ExportResult {
  return {
    exportId: "exp_1",
    status: "succeeded",
    format: "pdf",
    url: "/exports/exp_1/download?token=t",
    bytes: 40_000,
    error: null,
    ...overrides,
  };
}

describe("exportProgressNarration", () => {
  it("has distinct sentences for pending and running", () => {
    expect(exportProgressNarration("pending")).not.toBe(exportProgressNarration("running"));
  });
});

describe("exportOutcomeNarration", () => {
  it("reports success plainly", () => {
    const text = exportOutcomeNarration(result());
    expect(text).toBe("Your PDF is ready.");
  });

  it("reports the backend's own error on failure", () => {
    const text = exportOutcomeNarration(
      result({ status: "failed", error: "PlantUML render exceeded the size limit" }),
    );
    expect(text).toBe("The export failed: PlantUML render exceeded the size limit");
  });
});
