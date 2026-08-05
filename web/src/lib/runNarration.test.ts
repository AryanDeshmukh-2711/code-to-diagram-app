import { describe, expect, it } from "vitest";

import { runOutcomeNarration, runProgressNarration } from "./runNarration";
import type { Artefact, Run } from "./runs";

function artefact(overrides: Partial<Artefact> = {}): Artefact {
  return {
    diagramType: "class",
    title: "Class diagram",
    status: "succeeded",
    engine: "plantuml",
    error: null,
    attempts: 1,
    bytes: 100,
    cpmVersionId: "cpmv_1",
    originRunId: "run_1",
    carriedForward: false,
    ...overrides,
  };
}

function run(overrides: Partial<Run> = {}): Run {
  return {
    runId: "run_1",
    projectId: "proj_1",
    cpmVersionId: "cpmv_1",
    status: "succeeded",
    kind: "full",
    parentRunId: null,
    requestedTypes: ["class"],
    artefacts: [artefact()],
    durationMs: 1000,
    llmCostUsd: "0",
    attempts: 1,
    error: null,
    ...overrides,
  };
}

describe("runProgressNarration: never a generic placeholder", () => {
  it("has distinct sentences for pending and running", () => {
    const pending = runProgressNarration(run({ status: "pending", artefacts: [] }));
    const running = runProgressNarration(
      run({ status: "running", artefacts: [artefact({ status: "pending" })] }),
    );
    expect(pending).not.toBe(running);
  });

  it("reports live progress once something has finished", () => {
    const partial = runProgressNarration(
      run({
        status: "running",
        requestedTypes: ["class", "useCase"],
        artefacts: [
          artefact({ diagramType: "class", status: "succeeded" }),
          artefact({ diagramType: "useCase", status: "pending" }),
        ],
      }),
    );
    expect(partial).toContain("1 of 2");
  });
});

describe("runOutcomeNarration: a partial failure stays a partial failure", () => {
  it("names exactly which diagram failed and its own error, others still counted ready", () => {
    const result = runOutcomeNarration(
      run({
        status: "succeeded",
        artefacts: [
          artefact({ diagramType: "class", status: "succeeded" }),
          artefact({ diagramType: "useCase", status: "succeeded" }),
          artefact({ diagramType: "sequence", status: "succeeded" }),
          artefact({ diagramType: "activity", status: "succeeded" }),
          artefact({ diagramType: "state", status: "succeeded" }),
          artefact({ diagramType: "component", status: "succeeded" }),
          artefact({ diagramType: "deployment", status: "succeeded" }),
          artefact({
            diagramType: "entity_relationship",
            status: "failed",
            error: "PlantUML timed out",
          }),
        ],
      }),
    );
    expect(result).toBe(
      "7 of 8 diagrams ready; entity_relationship failed: PlantUML timed out.",
    );
  });

  it("never collapses a mixed result into a bare success line", () => {
    const result = runOutcomeNarration(
      run({
        artefacts: [
          artefact({ diagramType: "class", status: "succeeded" }),
          artefact({ diagramType: "useCase", status: "failed", error: "boom" }),
        ],
      }),
    );
    expect(result.toLowerCase()).not.toBe("done!");
    expect(result).toContain("failed");
  });

  it("lists every failure when more than one diagram failed", () => {
    const result = runOutcomeNarration(
      run({
        artefacts: [
          artefact({ diagramType: "class", status: "succeeded" }),
          artefact({ diagramType: "useCase", status: "failed", error: "err A" }),
          artefact({ diagramType: "sequence", status: "failed", error: "err B" }),
        ],
      }),
    );
    expect(result).toContain("useCase failed: err A");
    expect(result).toContain("sequence failed: err B");
  });
});

describe("runOutcomeNarration: skipped is distinct from failed", () => {
  it("counts and names skipped diagrams separately from failures", () => {
    const result = runOutcomeNarration(
      run({
        artefacts: [
          artefact({ diagramType: "class", status: "succeeded" }),
          artefact({ diagramType: "state", status: "skipped" }),
        ],
      }),
    );
    expect(result).toContain("1 skipped (state");
    expect(result).not.toContain("state failed");
  });

  it("a run with only successes and skips never mentions 'failed'", () => {
    const result = runOutcomeNarration(
      run({
        artefacts: [
          artefact({ diagramType: "class", status: "succeeded" }),
          artefact({ diagramType: "state", status: "skipped" }),
        ],
      }),
    );
    expect(result).not.toContain("failed");
  });
});

describe("runOutcomeNarration: total failure before any artefacts exist", () => {
  it("reports the run-level error honestly", () => {
    const result = runOutcomeNarration(
      run({ status: "failed", artefacts: [], error: "gateway unreachable" }),
    );
    expect(result).toBe("The run failed before any diagrams could be drawn: gateway unreachable");
  });
});
