/**
 * A visitor's own LLM API key, for a publicly hosted deployment where each
 * visitor brings their own credential instead of the operator paying for
 * everyone's usage.
 *
 * Lives only in this browser's localStorage — it is attached as a request
 * header (see `client.ts`) and never persisted server-side (see
 * `shared/llm/gateway.py`'s `api_key_override`, staged transiently in Redis
 * and read exactly once by the worker job that uses it).
 */

const STORAGE_KEY = "asa:llm-api-key";

export function getLlmApiKey(): string | null {
  if (typeof window === "undefined") return null;
  return window.localStorage.getItem(STORAGE_KEY);
}

export function setLlmApiKey(key: string | null): void {
  if (typeof window === "undefined") return;
  if (key && key.trim()) {
    window.localStorage.setItem(STORAGE_KEY, key.trim());
  } else {
    window.localStorage.removeItem(STORAGE_KEY);
  }
}

/** Whether this deployment expects visitors to supply their own key — a
 * hosted public demo sets this at build time; local self-hosting (Ollama,
 * no key needed) leaves it unset. */
export const LLM_KEY_REQUIRED = process.env.NEXT_PUBLIC_LLM_KEY_REQUIRED === "true";

export const LLM_PROVIDER_LABEL = process.env.NEXT_PUBLIC_LLM_PROVIDER_LABEL || "an OpenAI-compatible provider";

export const LLM_PROVIDER_SIGNUP_URL = process.env.NEXT_PUBLIC_LLM_PROVIDER_SIGNUP_URL || null;
