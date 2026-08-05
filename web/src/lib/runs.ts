import { apiFetch, streamJson } from "@/lib/client";

export type Artefact = {
  diagramType: string;
  title: string;
  status: string;
  engine: string | null;
  error: string | null;
  attempts: number;
  bytes: number | null;
  cpmVersionId: string | null;
  originRunId: string | null;
  carriedForward: boolean;
};

export type Run = {
  runId: string;
  projectId: string;
  cpmVersionId: string;
  status: string;
  kind: string;
  parentRunId: string | null;
  requestedTypes: string[];
  artefacts: Artefact[];
  durationMs: number | null;
  llmCostUsd: string | null;
  attempts: number;
  error: string | null;
};

export type StartRunInput = {
  projectId: string;
  cpmVersionId: string;
  diagramTypes?: string[];
  templateId?: string;
  format?: string;
};

/** 202: queues rendering and returns immediately (C-4). */
export async function startRun(input: StartRunInput): Promise<Run> {
  return apiFetch<Run>("/runs", { method: "POST", body: input });
}

export async function getRun(runId: string): Promise<Run> {
  return apiFetch<Run>(`/runs/${runId}`);
}

export type RegenerateInput = {
  diagramType: string;
  cpmVersionId?: string;
};

export type RegenerateResult = {
  changed: boolean;
  reason: string;
  diagramType: string;
  cpmVersionId: string;
  runId: string | null;
  previousStatus: string | null;
  staleTypes: string[];
};

/** 200 if nothing needed regenerating, 202 if a child run was queued — the
 * body tells you which happened via `changed`. */
export async function regenerate(runId: string, input: RegenerateInput): Promise<RegenerateResult> {
  return apiFetch<RegenerateResult>(`/runs/${runId}/regenerate`, { method: "POST", body: input });
}

export type LineageEntry = {
  runId: string;
  kind: string;
  status: string;
  regenerated: string[];
  cpmVersionId: string;
  createdAt: string | null;
  completedAt: string | null;
};

export async function runHistory(runId: string): Promise<LineageEntry[]> {
  return apiFetch<LineageEntry[]>(`/runs/${runId}/history`);
}

/** Live progress. Returns a function that stops listening. */
export function streamRun(runId: string, onUpdate: (run: Run) => void): () => void {
  return streamJson<Run>(`/runs/${runId}/events`, onUpdate);
}
