import { describe, expect, it } from "vitest";

import { extractionOutcomeNarration, extractionProgressNarration } from "./narration";
import type { Extraction } from "./extraction";

function extraction(overrides: Partial<Extraction> = {}): Extraction {
  return {
    extractionId: "ext_1",
    projectId: "proj_1",
    status: "succeeded",
    outcome: null,
    reason: null,
    guidance: [],
    notes: [],
    wordCount: null,
    entitiesFound: null,
    relationshipsFound: null,
    cpmDraftReady: false,
    error: null,
    ...overrides,
  };
}

describe("extractionProgressNarration: never a generic placeholder", () => {
  it("has a distinct sentence for pending", () => {
    expect(extractionProgressNarration("pending")).toBe(
      "Queued — I'll start reading it in just a moment.",
    );
  });

  it("has a distinct sentence for running", () => {
    expect(extractionProgressNarration("running")).toBe("Reading through it now…");
  });

  it("pending and running never read the same", () => {
    expect(extractionProgressNarration("pending")).not.toBe(extractionProgressNarration("running"));
  });

  it("reports an unexpected status rather than a placeholder", () => {
    expect(extractionProgressNarration("some_future_status")).toContain("some_future_status");
  });
});

describe("extractionOutcomeNarration: insufficient input, verbatim", () => {
  it("reproduces reason and guidance exactly, unedited", () => {
    const result = extraction({
      status: "succeeded",
      outcome: "insufficient",
      reason: "The description is 42 words long but only 1 entity could be identified.",
      guidance: [
        "Name the things the system stores or tracks.",
        "Say how those things relate to each other.",
      ],
    });
    const narration = extractionOutcomeNarration(result);
    expect(narration).toContain(
      "The description is 42 words long but only 1 entity could be identified.",
    );
    expect(narration).toContain("Name the things the system stores or tracks.");
    expect(narration).toContain("Say how those things relate to each other.");
  });

  it("does not add any sentence the backend did not supply", () => {
    const result = extraction({
      status: "succeeded",
      outcome: "insufficient",
      reason: "No entities could be identified in the description.",
      guidance: ["Describe what the system stores."],
    });
    const narration = extractionOutcomeNarration(result);
    const allowedText = "No entities could be identified in the description.\n• Describe what the system stores.";
    expect(narration).toBe(allowedText);
  });

  it("handles guidance being empty without inventing filler", () => {
    const result = extraction({ status: "succeeded", outcome: "insufficient", reason: "Too thin.", guidance: [] });
    expect(extractionOutcomeNarration(result)).toBe("Too thin.");
  });
});

describe("extractionOutcomeNarration: other terminal states", () => {
  it("reports a real extracted success", () => {
    const result = extraction({ status: "succeeded", outcome: "extracted" });
    expect(extractionOutcomeNarration(result)).toBe("Done — here's what I found.");
  });

  it("reports the actual backend error on failure", () => {
    const result = extraction({ status: "failed", outcome: null, error: "ProviderError: connection refused" });
    expect(extractionOutcomeNarration(result)).toBe(
      "That didn't work: ProviderError: connection refused",
    );
  });

  it("still says something honest if a failure carries no error text", () => {
    const result = extraction({ status: "failed", outcome: null, error: null });
    expect(extractionOutcomeNarration(result)).toBe(
      "That didn't work: an unexpected error happened.",
    );
  });

  it("does not silently swallow an outcome it does not recognise", () => {
    const result = extraction({ status: "succeeded", outcome: "something_new" as never });
    expect(extractionOutcomeNarration(result)).toContain("something_new");
  });
});
