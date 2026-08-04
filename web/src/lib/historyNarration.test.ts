import { describe, expect, it } from "vitest";

import { historyNarration } from "./historyNarration";
import type { LineageEntry } from "./runs";

function entry(overrides: Partial<LineageEntry> = {}): LineageEntry {
  return {
    runId: "run_1",
    kind: "full",
    status: "succeeded",
    regenerated: ["class", "use_case"],
    cpmVersionId: "cpmv_1",
    createdAt: "2026-08-05T10:00:00Z",
    completedAt: "2026-08-05T10:00:05Z",
    ...overrides,
  };
}

describe("historyNarration: conversational, in order", () => {
  it("reports an empty history honestly", () => {
    expect(historyNarration([])).toBe("Nothing has been generated for this project yet.");
  });

  it("lists entries in the order given, numbered", () => {
    const result = historyNarration([
      entry({ runId: "run_1", kind: "full" }),
      entry({ runId: "run_2", kind: "regeneration", regenerated: ["class"] }),
    ]);
    const lines = result.split("\n");
    expect(lines[0]).toMatch(/^1\./);
    expect(lines[1]).toMatch(/^2\./);
  });

  it("distinguishes a full run from a regeneration", () => {
    const result = historyNarration([
      entry({ kind: "full", regenerated: ["class", "use_case", "sequence"] }),
      entry({ kind: "regeneration", regenerated: ["class"] }),
    ]);
    expect(result).toContain("generated the full set");
    expect(result).toContain("regenerated class");
  });

  it("names which diagram types were actually touched at each step", () => {
    const result = historyNarration([entry({ kind: "regeneration", regenerated: ["entity_relationship"] })]);
    expect(result).toContain("entity_relationship");
  });
});
