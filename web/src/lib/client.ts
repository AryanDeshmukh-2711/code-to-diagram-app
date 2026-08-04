/**
 * The one place that knows the API's base URL and how to attach a session.
 *
 * Every other lib module (auth, review, runs, exports, extraction, chat)
 * calls `apiFetch` or `streamJson` rather than `fetch` directly. That is the
 * whole point: a second hand-rolled fetch wrapper is how a client silently
 * stops sending the Authorization header, or stops handling a 401, in one
 * corner of the app while every other corner keeps working.
 *
 * A 401 is handled once, here, for the same reason: whatever endpoint
 * produced it, the session is no longer good for anything, so the outcome —
 * clear it, send the user back to sign in — must be identical everywhere.
 */

import { clearSession, getToken } from "@/lib/session";

export const API_BASE_URL = process.env.NEXT_PUBLIC_API_BASE_URL ?? "http://localhost:8000";

export class ApiError extends Error {
  readonly status: number;

  constructor(status: number, message: string) {
    super(message);
    this.name = "ApiError";
    this.status = status;
  }
}

type Unauthorized = () => void;

const defaultUnauthorized: Unauthorized = () => {
  clearSession();
  if (typeof window !== "undefined") window.location.href = "/signin";
};

let onUnauthorized: Unauthorized = defaultUnauthorized;

/** Swaps the 401 handler. Only real caller is tests — production code never
 * needs a second way to react to a session going bad. */
export function _setUnauthorizedHandler(handler: Unauthorized): void {
  onUnauthorized = handler;
}

export function _resetUnauthorizedHandler(): void {
  onUnauthorized = defaultUnauthorized;
}

type RequestOptions = {
  method?: string;
  body?: unknown;
  /** Set for multipart uploads (extraction's PDF path) — `body` must already
   * be a FormData, and no Content-Type is set so the browser can add the
   * boundary itself. */
  isFormData?: boolean;
  signal?: AbortSignal;
};

export async function apiFetch<T>(path: string, options: RequestOptions = {}): Promise<T> {
  const headers: Record<string, string> = {};
  const token = getToken();
  if (token) headers.Authorization = `Bearer ${token}`;

  let body: BodyInit | undefined;
  if (options.body !== undefined) {
    if (options.isFormData) {
      body = options.body as FormData;
    } else {
      headers["Content-Type"] = "application/json";
      body = JSON.stringify(options.body);
    }
  }

  const response = await fetch(`${API_BASE_URL}${path}`, {
    method: options.method ?? (options.body !== undefined ? "POST" : "GET"),
    headers,
    body,
    signal: options.signal,
    cache: "no-store",
  });

  if (response.status === 401) {
    onUnauthorized();
    throw new ApiError(401, "Your session has expired. Please sign in again.");
  }

  if (!response.ok) {
    throw new ApiError(response.status, await _detail(response));
  }

  if (response.status === 204) return undefined as T;
  return (await response.json()) as T;
}

async function _detail(response: Response): Promise<string> {
  const body = await response.json().catch(() => null);
  if (body && typeof body.detail === "string") return body.detail;
  if (body && body.detail !== undefined) return JSON.stringify(body.detail);
  return response.statusText || `request failed with status ${response.status}`;
}

/**
 * Server-sent progress, consumed with `fetch` rather than `EventSource`.
 *
 * `EventSource` cannot set an Authorization header, and every progress stream
 * this product has (runs, extraction, chat) is behind one — so the frames are
 * read off the response body by hand instead. The wire format is unchanged:
 * one `data: {...}\n\n` per state change, connection closed by the server on
 * a terminal state.
 */
export function streamJson<T>(path: string, onEvent: (payload: T) => void): () => void {
  const controller = new AbortController();

  void (async () => {
    const headers: Record<string, string> = {};
    const token = getToken();
    if (token) headers.Authorization = `Bearer ${token}`;

    let response: Response;
    try {
      response = await fetch(`${API_BASE_URL}${path}`, {
        headers,
        signal: controller.signal,
        cache: "no-store",
      });
    } catch {
      return; // aborted, or the network dropped — nothing more to report
    }

    if (response.status === 401) {
      onUnauthorized();
      return;
    }
    if (!response.ok || !response.body) return;

    const reader = response.body.getReader();
    const decoder = new TextDecoder();
    let buffer = "";

    for (;;) {
      const { done, value } = await reader.read();
      if (done) return;
      buffer += decoder.decode(value, { stream: true });

      let boundary = buffer.indexOf("\n\n");
      while (boundary !== -1) {
        const frame = buffer.slice(0, boundary);
        buffer = buffer.slice(boundary + 2);
        const line = frame.split("\n").find((candidate) => candidate.startsWith("data: "));
        if (line) {
          try {
            onEvent(JSON.parse(line.slice("data: ".length)) as T);
          } catch {
            // one malformed frame does not end the stream
          }
        }
        boundary = buffer.indexOf("\n\n");
      }
    }
  })();

  return () => controller.abort();
}
