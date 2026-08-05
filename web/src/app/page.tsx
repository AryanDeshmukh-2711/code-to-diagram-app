"use client";

import { useEffect, useState } from "react";
import Link from "next/link";
import { useRouter } from "next/navigation";

import { ApiError } from "@/lib/client";
import { deleteProject, listProjects, type Project } from "@/lib/projects";
import { isAuthed } from "@/lib/session";
import { Button } from "@/components/ui/button";
import { Card, CardContent } from "@/components/ui/card";

/**
 * The home screen: start something new, or come back to what already
 * exists. FR-23's list/open/delete — "your projects" is not shown as a
 * courtesy, it is how someone who has hit their tier's project limit finds
 * out what there is to delete, since nothing else in the product surfaces
 * that. Deleting itself needs a second, explicit click (SRS UI-5) rather
 * than acting on the first one — a destructive action that fires from a
 * single click is exactly what that requirement exists to prevent.
 */
export default function Home() {
  const router = useRouter();
  const [checked, setChecked] = useState(false);
  const [projects, setProjects] = useState<Project[] | null>(null);
  const [loadError, setLoadError] = useState<string | null>(null);
  const [confirmingId, setConfirmingId] = useState<string | null>(null);
  const [deletingId, setDeletingId] = useState<string | null>(null);

  useEffect(() => {
    if (!isAuthed()) {
      router.replace("/signin");
      return;
    }
    setChecked(true);
  }, [router]);

  useEffect(() => {
    if (!checked) return;
    listProjects()
      .then(setProjects)
      .catch((error) =>
        setLoadError(
          error instanceof ApiError ? error.message : "Something went wrong loading your projects.",
        ),
      );
  }, [checked]);

  if (!checked) return null;

  const newProjectId = `proj_${Math.random().toString(36).slice(2, 10)}`;

  async function onDelete(projectId: string) {
    setDeletingId(projectId);
    setLoadError(null);
    try {
      await deleteProject(projectId);
      setProjects((current) => (current ?? []).filter((p) => p.projectId !== projectId));
    } catch (error) {
      setLoadError(
        error instanceof ApiError ? error.message : "Something went wrong deleting that.",
      );
    } finally {
      setDeletingId(null);
      setConfirmingId(null);
    }
  }

  return (
    <main className="mx-auto flex min-h-screen max-w-2xl flex-col justify-center gap-6 p-8">
      <div className="flex flex-col gap-4">
        <h1 className="text-2xl font-semibold tracking-tight">AI Software Architect</h1>
        <p className="text-sm text-muted-foreground">
          Drop a PDF or paste a description and I&apos;ll turn it into a reviewable model.
        </p>
        <div className="flex flex-wrap gap-3">
          <Button asChild className="w-fit">
            <Link href={`/projects/${newProjectId}/chat`}>Start a new project</Link>
          </Button>
          <Button asChild variant="outline" className="w-fit">
            <Link href="/review/demo">Open the sample project</Link>
          </Button>
        </div>
      </div>

      {projects && projects.length > 0 ? (
        <div className="flex flex-col gap-2">
          <h2 className="text-sm font-medium text-muted-foreground">Your projects</h2>
          {loadError ? <p className="text-sm text-destructive">{loadError}</p> : null}
          <div className="flex flex-col gap-2">
            {projects.map((project) => (
              <Card key={project.projectId}>
                <CardContent className="flex items-center justify-between gap-3 py-3">
                  <Link
                    href={`/projects/${project.projectId}/chat`}
                    className="min-w-0 flex-1 truncate text-sm font-medium hover:underline"
                  >
                    {project.name || project.projectId}
                  </Link>
                  {confirmingId === project.projectId ? (
                    <div className="flex shrink-0 items-center gap-2">
                      <span className="text-xs text-muted-foreground">Delete this project?</span>
                      <Button
                        size="sm"
                        variant="destructive"
                        disabled={deletingId === project.projectId}
                        onClick={() => void onDelete(project.projectId)}
                      >
                        {deletingId === project.projectId ? "Deleting…" : "Delete"}
                      </Button>
                      <Button size="sm" variant="ghost" onClick={() => setConfirmingId(null)}>
                        Cancel
                      </Button>
                    </div>
                  ) : (
                    <Button
                      size="sm"
                      variant="ghost"
                      className="shrink-0 text-muted-foreground hover:text-destructive"
                      onClick={() => setConfirmingId(project.projectId)}
                    >
                      Delete
                    </Button>
                  )}
                </CardContent>
              </Card>
            ))}
          </div>
        </div>
      ) : null}
    </main>
  );
}
