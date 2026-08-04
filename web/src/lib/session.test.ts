import { beforeEach, describe, expect, it, vi } from "vitest";

import { clearSession, getToken, isAuthed, setToken } from "./session";

function fakeLocalStorage(): Storage {
  const store = new Map<string, string>();
  return {
    getItem: (key: string) => store.get(key) ?? null,
    setItem: (key: string, value: string) => void store.set(key, value),
    removeItem: (key: string) => void store.delete(key),
    clear: () => store.clear(),
    key: (index: number) => Array.from(store.keys())[index] ?? null,
    get length() {
      return store.size;
    },
  } as Storage;
}

beforeEach(() => {
  vi.stubGlobal("window", { localStorage: fakeLocalStorage() });
});

describe("session", () => {
  it("has no token before one is set", () => {
    expect(getToken()).toBeNull();
    expect(isAuthed()).toBe(false);
  });

  it("stores and returns exactly the token it was given", () => {
    setToken("tok_abc123");
    expect(getToken()).toBe("tok_abc123");
    expect(isAuthed()).toBe(true);
  });

  it("clears the token on sign-out", () => {
    setToken("tok_abc123");
    clearSession();
    expect(getToken()).toBeNull();
    expect(isAuthed()).toBe(false);
  });

  it("does nothing rather than throw when there is no window (SSR)", () => {
    vi.stubGlobal("window", undefined);
    expect(() => setToken("x")).not.toThrow();
    expect(getToken()).toBeNull();
    expect(() => clearSession()).not.toThrow();
  });
});
