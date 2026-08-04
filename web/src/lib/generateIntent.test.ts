import { describe, expect, it } from "vitest";

import { looksLikeGenerateRequest } from "./generateIntent";

describe("looksLikeGenerateRequest", () => {
  it("recognises the canonical phrase", () => {
    expect(looksLikeGenerateRequest("generate the diagrams")).toBe(true);
  });

  it("recognises other generate-verbs paired with 'diagram'", () => {
    expect(looksLikeGenerateRequest("draw the diagrams now")).toBe(true);
    expect(looksLikeGenerateRequest("can you render the diagrams?")).toBe(true);
    expect(looksLikeGenerateRequest("please make a diagram of this")).toBe(true);
    expect(looksLikeGenerateRequest("build the diagram set")).toBe(true);
  });

  it("is case-insensitive", () => {
    expect(looksLikeGenerateRequest("GENERATE THE DIAGRAMS")).toBe(true);
  });

  it("does not fire on an edit request that shares no vocabulary", () => {
    expect(looksLikeGenerateRequest("rename Book to Publication")).toBe(false);
    expect(looksLikeGenerateRequest("add a dueDate attribute to Loan")).toBe(false);
    expect(looksLikeGenerateRequest("delete the Fine entity")).toBe(false);
  });

  it("does not fire on a plain question", () => {
    expect(looksLikeGenerateRequest("how's it going?")).toBe(false);
    expect(looksLikeGenerateRequest("what does this model cover?")).toBe(false);
  });

  it("requires both a generate-verb and 'diagram' present", () => {
    expect(looksLikeGenerateRequest("generate it")).toBe(false);
    expect(looksLikeGenerateRequest("I like this diagram")).toBe(false);
  });
});
