/**
 * Where the session token lives, and the one thing that must never end up
 * here: the API key. The key proves who you are once, at sign-in; the token
 * is what every request after that carries, and it is all this module ever
 * touches.
 */

const TOKEN_KEY = "asa.session.token";

function storage(): Storage | null {
  // Next.js renders this module on the server too, where there is no
  // localStorage at all — every function here has to survive that.
  if (typeof window === "undefined") return null;
  return window.localStorage;
}

export function getToken(): string | null {
  return storage()?.getItem(TOKEN_KEY) ?? null;
}

export function setToken(token: string): void {
  storage()?.setItem(TOKEN_KEY, token);
}

export function clearSession(): void {
  storage()?.removeItem(TOKEN_KEY);
}

export function isAuthed(): boolean {
  return getToken() !== null;
}
