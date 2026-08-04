import { describe, expect, it } from "vitest";

import { looksLikeHistoryRequest } from "./historyIntent";

describe("looksLikeHistoryRequest", () => {
  it("recognises the canonical question", () => {
    expect(looksLikeHistoryRequest("what have I changed?")).toBe(true);
  });

  it("recognises other natural phrasings", () => {
    expect(looksLikeHistoryRequest("what's changed so far?")).toBe(true);
    expect(looksLikeHistoryRequest("what did I regenerate?")).toBe(true);
    expect(looksLikeHistoryRequest("show me the history")).toBe(true);
    expect(looksLikeHistoryRequest("can I see the change log?")).toBe(true);
    expect(looksLikeHistoryRequest("changelog please")).toBe(true);
  });

  it("does not fire on an edit request or a plain question", () => {
    expect(looksLikeHistoryRequest("rename Book to Publication")).toBe(false);
    expect(looksLikeHistoryRequest("redraw the class diagram")).toBe(false);
    expect(looksLikeHistoryRequest("how's it going?")).toBe(false);
  });
});
