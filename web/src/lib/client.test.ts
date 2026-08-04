import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

import { ApiError, _resetUnauthorizedHandler, _setUnauthorizedHandler, apiFetch } from "./client";
import { clearSession, setToken } from "./session";

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

function jsonResponse(status: number, body: unknown): Response {
  return new Response(JSON.stringify(body), {
    status,
    headers: { "content-type": "application/json" },
  });
}

beforeEach(() => {
  vi.stubGlobal("window", { localStorage: fakeLocalStorage() });
});

afterEach(() => {
  clearSession();
  _resetUnauthorizedHandler();
  vi.unstubAllGlobals();
});

describe("apiFetch: the auth header", () => {
  it("attaches Authorization when a session exists", async () => {
    setToken("tok_abc");
    const fetchMock = vi.fn().mockResolvedValue(jsonResponse(200, { ok: true }));
    vi.stubGlobal("fetch", fetchMock);

    await apiFetch("/whatever");

    const [, init] = fetchMock.mock.calls[0];
    expect(init.headers.Authorization).toBe("Bearer tok_abc");
  });

  it("sends no Authorization header when signed out", async () => {
    const fetchMock = vi.fn().mockResolvedValue(jsonResponse(200, { ok: true }));
    vi.stubGlobal("fetch", fetchMock);

    await apiFetch("/whatever");

    const [, init] = fetchMock.mock.calls[0];
    expect(init.headers.Authorization).toBeUndefined();
  });
});

describe("apiFetch: a 401 produces the same outcome everywhere", () => {
  it("calls the unauthorized handler and throws ApiError(401)", async () => {
    const handler = vi.fn();
    _setUnauthorizedHandler(handler);
    vi.stubGlobal("fetch", vi.fn().mockResolvedValue(jsonResponse(401, { detail: "expired" })));

    await expect(apiFetch("/projects/x/review")).rejects.toThrow(ApiError);
    expect(handler).toHaveBeenCalledOnce();
  });

  it("the outcome is identical regardless of which endpoint returned the 401", async () => {
    const handler = vi.fn();
    _setUnauthorizedHandler(handler);
    vi.stubGlobal("fetch", vi.fn().mockResolvedValue(jsonResponse(401, { detail: "expired" })));

    for (const path of ["/runs/r1", "/projects/p1/chat", "/exports/e1", "/auth/token"]) {
      await expect(apiFetch(path)).rejects.toThrow(ApiError);
    }
    expect(handler).toHaveBeenCalledTimes(4);
  });
});

describe("apiFetch: other failures", () => {
  it("throws ApiError carrying the server's detail message", async () => {
    vi.stubGlobal(
      "fetch",
      vi.fn().mockResolvedValue(jsonResponse(409, { detail: "No entity with id 'x' exists." })),
    );

    const error = await apiFetch("/projects/p1/review/edit").catch((e) => e);
    expect(error).toBeInstanceOf(ApiError);
    expect((error as ApiError).status).toBe(409);
    expect((error as ApiError).message).toBe("No entity with id 'x' exists.");
  });

  it("stringifies a structured detail rather than dropping it", async () => {
    vi.stubGlobal(
      "fetch",
      vi.fn().mockResolvedValue(
        jsonResponse(409, { detail: { code: "needs_png", message: "generate a PNG first" } }),
      ),
    );

    const error = await apiFetch("/runs/r1/export").catch((e) => e);
    expect(error).toBeInstanceOf(ApiError);
    expect((error as ApiError).message).toContain("needs_png");
  });
});

describe("apiFetch: request shape", () => {
  it("JSON-encodes a plain body and sets Content-Type", async () => {
    const fetchMock = vi.fn().mockResolvedValue(jsonResponse(200, {}));
    vi.stubGlobal("fetch", fetchMock);

    await apiFetch("/projects/p1/chat", { method: "POST", body: { message: "hi" } });

    const [, init] = fetchMock.mock.calls[0];
    expect(init.headers["Content-Type"]).toBe("application/json");
    expect(init.body).toBe(JSON.stringify({ message: "hi" }));
  });

  it("passes FormData through untouched, with no Content-Type", async () => {
    const fetchMock = vi.fn().mockResolvedValue(jsonResponse(200, {}));
    vi.stubGlobal("fetch", fetchMock);

    const form = new FormData();
    form.set("text", "a description");
    await apiFetch("/projects/p1/extract", { method: "POST", body: form, isFormData: true });

    const [, init] = fetchMock.mock.calls[0];
    expect(init.body).toBe(form);
    expect(init.headers["Content-Type"]).toBeUndefined();
  });

  it("returns the parsed body on success", async () => {
    vi.stubGlobal("fetch", vi.fn().mockResolvedValue(jsonResponse(200, { status: "pending" })));

    const result = await apiFetch<{ status: string }>("/runs/r1");
    expect(result.status).toBe("pending");
  });
});
