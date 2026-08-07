import { afterEach, describe, expect, it, vi } from "vitest";

import { getLlmApiKey, setLlmApiKey } from "./llmKey";

function fakeLocalStorage() {
  const store = new Map<string, string>();
  return {
    getItem: (key: string) => store.get(key) ?? null,
    setItem: (key: string, value: string) => void store.set(key, value),
    removeItem: (key: string) => void store.delete(key),
  };
}

afterEach(() => {
  vi.unstubAllGlobals();
});

describe("llmKey: browser-only storage", () => {
  it("round-trips a key through localStorage", () => {
    vi.stubGlobal("window", { localStorage: fakeLocalStorage() });

    expect(getLlmApiKey()).toBeNull();
    setLlmApiKey("gsk_test_key");
    expect(getLlmApiKey()).toBe("gsk_test_key");
  });

  it("trims whitespace before storing", () => {
    vi.stubGlobal("window", { localStorage: fakeLocalStorage() });

    setLlmApiKey("  gsk_test_key  ");
    expect(getLlmApiKey()).toBe("gsk_test_key");
  });

  it("clears the stored key when set to null or blank", () => {
    vi.stubGlobal("window", { localStorage: fakeLocalStorage() });

    setLlmApiKey("gsk_test_key");
    setLlmApiKey(null);
    expect(getLlmApiKey()).toBeNull();

    setLlmApiKey("gsk_test_key");
    setLlmApiKey("   ");
    expect(getLlmApiKey()).toBeNull();
  });

  it("never throws when there is no window (server-side rendering)", () => {
    expect(() => getLlmApiKey()).not.toThrow();
    expect(getLlmApiKey()).toBeNull();
    expect(() => setLlmApiKey("gsk_test_key")).not.toThrow();
  });
});
