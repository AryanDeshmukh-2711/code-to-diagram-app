import type { CPM } from "@/lib/cpm.generated";

const API = process.env.NEXT_PUBLIC_API_BASE_URL ?? "http://localhost:8000";

/** A draft is a CPM whose references may not resolve yet — that is the point
 * of the review screen. Reusing the generated CPM type keeps the shape honest;
 * only `meta` is absent until the model is confirmed. */
export type Draft = Omit<CPM, "meta"> & { meta?: CPM["meta"] };

export type Issue = {
  code: string;
  path: string;
  message: string;
  /** Written for someone who has never seen a UML diagram. Show this one. */
  explanation: string;
  offendingId: string | null;
};

export type Review = {
  projectId: string;
  projectName: string;
  draft: Draft;
  issues: Issue[];
  confirmable: boolean;
  counts: { entities: number; relationships: number; actors: number; useCases: number };
  lastEdit: string | null;
  referencesUpdated: number;
};

export type Edit =
  | { op: "rename_entity" | "rename_actor" | "rename_use_case"; id: string; name: string }
  | { op: "delete_entity" | "delete_actor" | "delete_relationship" | "delete_use_case"; id: string }
  | { op: "add_entity" | "add_actor"; name: string }
  | { op: "add_attribute"; entityId: string; attributeName: string; attributeType: string }
  | { op: "delete_attribute"; entityId: string; attributeName: string }
  | { op: "add_relationship"; fromId: string; toId: string; type: string }
  | {
      op: "relink_relationship";
      id: string;
      fromId?: string;
      toId?: string;
      type?: string;
      label?: string;
      cardinality?: string;
    }
  | { op: "set_use_case_actors"; id: string; actorIds: string[] };

export class ReviewRefused extends Error {}

async function unwrap(response: Response) {
  if (response.ok) return response.json();
  const body = await response.json().catch(() => ({ detail: response.statusText }));
  // 409 and 422 are the server refusing an edit or a confirmation — both are
  // messages for the user, not faults to log and hide.
  throw new ReviewRefused(body.detail ?? "Something went wrong.");
}

const json = { "content-type": "application/json" };

export async function loadReview(projectId: string): Promise<Review> {
  return unwrap(await fetch(`${API}/projects/${projectId}/review`, { cache: "no-store" }));
}

export async function seedReview(projectId: string, projectName: string): Promise<Review> {
  return unwrap(
    await fetch(`${API}/projects/${projectId}/review/seed`, {
      method: "POST",
      headers: json,
      body: JSON.stringify({ projectName }),
    }),
  );
}

export async function applyEdit(projectId: string, edit: Edit): Promise<Review> {
  return unwrap(
    await fetch(`${API}/projects/${projectId}/review/edit`, {
      method: "POST",
      headers: json,
      body: JSON.stringify(edit),
    }),
  );
}

export async function confirmReview(
  projectId: string,
): Promise<{ versionId: string; version: number; confirmedAt: string }> {
  return unwrap(
    await fetch(`${API}/projects/${projectId}/review/confirm`, { method: "POST" }),
  );
}

/** Issues that belong to one row, so the message lands next to the field. */
export function issuesAt(issues: Issue[], prefix: string): Issue[] {
  return issues.filter((issue) => issue.path.startsWith(prefix));
}
