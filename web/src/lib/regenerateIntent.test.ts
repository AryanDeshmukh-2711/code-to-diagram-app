import { describe, expect, it } from "vitest";

import { looksLikeRegenerateRequest } from "./regenerateIntent";

describe("looksLikeRegenerateRequest", () => {
  it("recognises the canonical phrase and maps to the backend's type string", () => {
    expect(looksLikeRegenerateRequest("redraw the class diagram")).toEqual({
      diagramType: "class",
    });
  });

  it("recognises every registered diagram type by its natural name", () => {
    expect(looksLikeRegenerateRequest("regenerate the use case diagram")).toEqual({
      diagramType: "use_case",
    });
    expect(looksLikeRegenerateRequest("redraw the entity relationship diagram")).toEqual({
      diagramType: "entity_relationship",
    });
    expect(looksLikeRegenerateRequest("recreate the sequence diagram")).toEqual({
      diagramType: "sequence",
    });
    expect(looksLikeRegenerateRequest("redo the activity diagram")).toEqual({
      diagramType: "activity",
    });
    expect(looksLikeRegenerateRequest("refresh the state diagram")).toEqual({
      diagramType: "state",
    });
    expect(looksLikeRegenerateRequest("redraw the component diagram")).toEqual({
      diagramType: "component",
    });
    expect(looksLikeRegenerateRequest("redraw the deployment diagram")).toEqual({
      diagramType: "deployment",
    });
  });

  it("returns null for a regenerate verb with no diagram named", () => {
    expect(looksLikeRegenerateRequest("regenerate the diagrams")).toBeNull();
    expect(looksLikeRegenerateRequest("redo that")).toBeNull();
  });

  it("returns null when no regenerate verb is present at all", () => {
    expect(looksLikeRegenerateRequest("the class diagram looks great")).toBeNull();
    expect(looksLikeRegenerateRequest("rename Book to Publication")).toBeNull();
  });

  it("does not fire on a plain edit request", () => {
    expect(looksLikeRegenerateRequest("add a dueDate attribute to Loan")).toBeNull();
  });
});
