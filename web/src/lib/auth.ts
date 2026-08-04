import { apiFetch } from "@/lib/client";
import { clearSession, setToken } from "@/lib/session";

export type RegisterInput = {
  email?: string;
  tier?: string;
};

export type RegisterResult = {
  accountId: string;
  apiKey: string;
  note: string;
};

/** Creates an account and returns its one key. Callers must show `apiKey` to
 * the user immediately and then let it go — nothing in this module persists
 * it, and the server cannot show it again either. */
export async function register(input: RegisterInput = {}): Promise<RegisterResult> {
  return apiFetch<RegisterResult>("/auth/register", { method: "POST", body: input });
}

export type SignInResult = {
  token: string;
  expiresInSeconds: number;
};

/** Trades an account id and its key for a session, and stores the session —
 * never the key, which this function does not even keep past the call. */
export async function signIn(accountId: string, apiKey: string): Promise<SignInResult> {
  const result = await apiFetch<SignInResult>("/auth/token", {
    method: "POST",
    body: { accountId, apiKey },
  });
  setToken(result.token);
  return result;
}

export function signOut(): void {
  clearSession();
}
