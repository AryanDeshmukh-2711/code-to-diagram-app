import { apiFetch, ApiError } from "@/lib/client";
import type { CPM } from "@/lib/cpm.generated";

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

/** review.py's own refusals (404 no draft, 409 an edit that fails validation,
 * 422 not confirmable) are all messages meant for the user, not faults to log
 * and hide — so every ApiError from this module surfaces as one. */
async function asReview<T>(promise: Promise<T>): Promise<T> {
  try {
    return await promise;
  } catch (error) {
    if (error instanceof ApiError) throw new ReviewRefused(error.message);
    throw error;
  }
}

export async function loadReview(projectId: string): Promise<Review> {
  return asReview(apiFetch<Review>(`/projects/${projectId}/review`));
}

export async function seedReview(projectId: string, projectName: string): Promise<Review> {
  return asReview(
    apiFetch<Review>(`/projects/${projectId}/review/seed`, {
      method: "POST",
      body: { projectName },
    }),
  );
}

export async function applyEdit(projectId: string, edit: Edit): Promise<Review> {
  return asReview(
    apiFetch<Review>(`/projects/${projectId}/review/edit`, { method: "POST", body: edit }),
  );
}

export async function confirmReview(
  projectId: string,
): Promise<{ versionId: string; version: number; confirmedAt: string }> {
  // No body, matching the server's own distinction: a confirm sent with no
  // review-signals payload is not attributed to an account in the funnel
  // event (see review.py's confirm()) — a later prompt wires the signals
  // this screen already tracks (lastEdit, referencesUpdated) into a real
  // ConfirmIn body.
  return asReview(apiFetch(`/projects/${projectId}/review/confirm`, { method: "POST" }));
}

/** Issues that belong to one row, so the message lands next to the field. */
export function issuesAt(issues: Issue[], prefix: string): Issue[] {
  return issues.filter((issue) => issue.path.startsWith(prefix));
}
