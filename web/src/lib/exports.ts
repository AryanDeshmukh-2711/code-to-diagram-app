import { API_BASE_URL, apiFetch } from "@/lib/client";

export type ExportInput = {
  format?: string;
  templateId?: string;
  fields?: Record<string, string>;
};

export type ExportResult = {
  exportId: string;
  status: string;
  format: string;
  url: string | null;
  bytes: number | null;
  error: string | null;
};

/** 202: queues rendering and returns immediately (C-4). */
export async function requestExport(runId: string, input: ExportInput = {}): Promise<ExportResult> {
  return apiFetch<ExportResult>(`/runs/${runId}/export`, { method: "POST", body: input });
}

export async function getExport(exportId: string): Promise<ExportResult> {
  return apiFetch<ExportResult>(`/exports/${exportId}`);
}

export type ArtefactLink = {
  diagramType: string;
  format: string;
  bytes: number;
  url: string;
};

export async function listArtefactLinks(
  runId: string,
): Promise<{ runId: string; artefacts: ArtefactLink[] }> {
  return apiFetch(`/runs/${runId}/artefacts`);
}

/** Export downloads and artefact images come back as signed, expiring paths
 * (NFR-S4) — the signature in the URL is the authorization, so these are
 * opened directly (`<a href>`, `<img src>`), never through `apiFetch`, and
 * never carry a bearer token. This only adds the host. */
export function absoluteUrl(path: string): string {
  return `${API_BASE_URL}${path}`;
}
