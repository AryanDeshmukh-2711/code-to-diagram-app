import { apiFetch } from "@/lib/client";

export type Project = {
  projectId: string;
  name: string;
  createdAt: string;
};

/** Every project, most recently created first (FR-23). */
export async function listProjects(): Promise<Project[]> {
  return apiFetch<Project[]>("/projects");
}

/** Deletes a project and everything it produced (FR-23, FR-24). 204 on
 * success — there is nothing left to return. */
export async function deleteProject(projectId: string): Promise<void> {
  await apiFetch<void>(`/projects/${projectId}`, { method: "DELETE" });
}
