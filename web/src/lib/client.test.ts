import { afterEach, describe, expect, it, vi } from "vitest";

import { ApiError, apiFetch } from "./client";

function jsonResponse(status: number, body: unknown): Response {
  return new Response(JSON.stringify(body), {
    status,
    headers: { "content-type": "application/json" },
  });
}

afterEach(() => {
  vi.unstubAllGlobals();
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

  it("splits a structured detail into code and message rather than dropping either", async () => {
    vi.stubGlobal(
      "fetch",
      vi.fn().mockResolvedValue(
        jsonResponse(409, { detail: { code: "needs_png", message: "generate a PNG first" } }),
      ),
    );

    const error = await apiFetch("/runs/r1/export").catch((e) => e);
    expect(error).toBeInstanceOf(ApiError);
    expect((error as ApiError).code).toBe("needs_png");
    expect((error as ApiError).message).toBe("generate a PNG first");
  });

  it("carries the full structured detail for callers that need more than code/message", async () => {
    vi.stubGlobal(
      "fetch",
      vi.fn().mockResolvedValue(
        jsonResponse(409, {
          detail: {
            code: "missing_fields",
            message: "template 'course-hand-in' needs values for: course_code",
            missing: ["course_code (Course code)"],
          },
        }),
      ),
    );

    const error = await apiFetch("/runs/r1/export").catch((e) => e);
    expect(error).toBeInstanceOf(ApiError);
    expect((error as ApiError).code).toBe("missing_fields");
    expect((error as ApiError).detail).toMatchObject({ missing: ["course_code (Course code)"] });
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
