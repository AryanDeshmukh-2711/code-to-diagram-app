import { describe, expect, it } from "vitest";

import { chatEditOutcomeNarration, chatEditProgressNarration } from "./chatEditNarration";
import type { ChatEdit } from "./chat";

function edit(overrides: Partial<ChatEdit> = {}): ChatEdit {
  return {
    editId: "chat_1",
    projectId: "proj_1",
    status: "succeeded",
    outcome: null,
    appliedOp: null,
    summary: null,
    referencesUpdated: null,
    clarifyQuestion: null,
    reason: null,
    error: null,
    ...overrides,
  };
}

describe("chatEditProgressNarration: never a generic placeholder", () => {
  it("has distinct sentences for pending and running", () => {
    const pending = chatEditProgressNarration("pending");
    const running = chatEditProgressNarration("running");
    expect(pending).not.toBe(running);
    expect(pending.length).toBeGreaterThan(0);
    expect(running.length).toBeGreaterThan(0);
  });
});

describe("chatEditOutcomeNarration: applied edits never say just 'Done!'", () => {
  it("names the summary and the exact reference count", () => {
    const result = chatEditOutcomeNarration(
      edit({
        outcome: "applied",
        appliedOp: "rename_entity",
        summary: "Renamed “Book” to “Publication”",
        referencesUpdated: 4,
      }),
    );
    expect(result).toBe('Renamed “Book” to “Publication”. Updated 4 references.');
    expect(result.toLowerCase()).not.toBe("done!");
  });

  it("still reports the count when it is zero, rather than omitting it", () => {
    const result = chatEditOutcomeNarration(
      edit({ outcome: "applied", summary: "Deleted relationship", referencesUpdated: 0 }),
    );
    expect(result).toBe("Deleted relationship. Updated 0 references.");
  });

  it("uses singular 'reference' for exactly one", () => {
    const result = chatEditOutcomeNarration(
      edit({ outcome: "applied", summary: "Renamed “Loan” to “Checkout”", referencesUpdated: 1 }),
    );
    expect(result).toContain("Updated 1 reference.");
    expect(result).not.toContain("1 references");
  });
});

describe("chatEditOutcomeNarration: a clarifying question is the model's own text", () => {
  it("shows the question verbatim, unprefixed", () => {
    const result = chatEditOutcomeNarration(
      edit({ outcome: "clarify", clarifyQuestion: "Did you mean Book or Loan?" }),
    );
    expect(result).toBe("Did you mean Book or Loan?");
  });
});

describe("chatEditOutcomeNarration: a rejected edit shows the API's exact message", () => {
  it("reproduces `reason` with nothing added", () => {
    const result = chatEditOutcomeNarration(
      edit({ outcome: "rejected", reason: "No entity with id 'invoice' exists in this model." }),
    );
    expect(result).toBe("No entity with id 'invoice' exists in this model.");
  });
});

describe("chatEditOutcomeNarration: other outcomes", () => {
  it("reports a non-edit message honestly", () => {
    const result = chatEditOutcomeNarration(edit({ outcome: "not_edit" }));
    expect(result.length).toBeGreaterThan(0);
    expect(result.toLowerCase()).not.toBe("done!");
  });

  it("reports the actual backend error on a system failure", () => {
    const result = chatEditOutcomeNarration(
      edit({ status: "failed", outcome: null, error: "SchemaValidationFailed: bad output" }),
    );
    expect(result).toBe("That didn't work: SchemaValidationFailed: bad output");
  });

  it("does not silently swallow an outcome it does not recognise", () => {
    const result = chatEditOutcomeNarration(edit({ outcome: "something_new" }));
    expect(result).toContain("something_new");
  });
});
