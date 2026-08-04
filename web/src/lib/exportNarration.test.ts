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
    watermarked: false,
    tier: "free",
    ...overrides,
  };
}

describe("exportProgressNarration", () => {
  it("has distinct sentences for pending and running", () => {
    expect(exportProgressNarration("pending")).not.toBe(exportProgressNarration("running"));
  });
});

describe("exportOutcomeNarration", () => {
  it("reports success plainly, with no watermark mention when there is none", () => {
    const text = exportOutcomeNarration(result({ watermarked: false }));
    expect(text).toBe("Your PDF is ready.");
  });

  it("mentions the watermark only when the backend's own field says so", () => {
    const text = exportOutcomeNarration(result({ watermarked: true }));
    expect(text).toBe("Your PDF is ready. It carries a watermark.");
  });

  it("reports the backend's own error on failure", () => {
    const text = exportOutcomeNarration(
      result({ status: "failed", error: "PlantUML render exceeded the size limit" }),
    );
    expect(text).toBe("The export failed: PlantUML render exceeded the size limit");
  });
});
