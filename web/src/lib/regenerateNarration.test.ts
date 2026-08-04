import { describe, expect, it } from "vitest";

import { regeneratePlanNarration } from "./regenerateNarration";
import type { RegenerateResult } from "./runs";

function result(overrides: Partial<RegenerateResult> = {}): RegenerateResult {
  return {
    changed: false,
    reason: "the model has not changed since this diagram was drawn",
    diagramType: "class",
    cpmVersionId: "cpmv_1",
    runId: null,
    previousStatus: "succeeded",
    staleTypes: [],
    ...overrides,
  };
}

describe("regeneratePlanNarration: a no-op is reported verbatim", () => {
  it("shows exactly the backend's reason, unedited, when nothing changed", () => {
    const backendReason =
      "the model has not changed since this diagram was drawn, and the " +
      "renderer is deterministic — regenerating would produce a byte-identical file";
    const narration = regeneratePlanNarration(result({ changed: false, reason: backendReason }));
    expect(narration).toBe(backendReason);
  });

  it("adds nothing before or after the reason on a no-op", () => {
    const narration = regeneratePlanNarration(result({ changed: false, reason: "unchanged." }));
    expect(narration).toBe("unchanged.");
  });

  it("shows the insufficient-model-data reason verbatim too", () => {
    const backendReason = "the model still does not describe this diagram: no states declared";
    const narration = regeneratePlanNarration(result({ changed: false, reason: backendReason }));
    expect(narration).toBe(backendReason);
  });
});

describe("regeneratePlanNarration: a real change names the diagram and mentions stale neighbours", () => {
  it("names the diagram being redrawn and includes the reason", () => {
    const narration = regeneratePlanNarration(
      result({ changed: true, diagramType: "class", reason: "entities were renamed" }),
    );
    expect(narration).toContain("class");
    expect(narration).toContain("entities were renamed");
  });

  it("mentions diagrams that will go stale once this one redraws", () => {
    const narration = regeneratePlanNarration(
      result({ changed: true, staleTypes: ["use_case", "sequence"] }),
    );
    expect(narration).toContain("use_case, sequence");
  });

  it("says nothing about staleness when there is none", () => {
    const narration = regeneratePlanNarration(result({ changed: true, staleTypes: [] }));
    expect(narration).not.toContain("stale");
  });
});
