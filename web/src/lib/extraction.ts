import { apiFetch, streamJson } from "@/lib/client";

export type Extraction = {
  extractionId: string;
  projectId: string;
  status: string;
  outcome: string | null;
  reason: string | null;
  guidance: string[];
  notes: string[];
  wordCount: number | null;
  entitiesFound: number | null;
  relationshipsFound: number | null;
  cpmDraftReady: boolean;
  error: string | null;
};

/** 202: queues extraction and returns immediately — the model never runs in
 * this request (C-4). */
export async function extractFromText(
  projectId: string,
  text: string,
  projectName: string,
): Promise<Extraction> {
  const body = new FormData();
  body.set("text", text);
  body.set("projectName", projectName);
  return apiFetch<Extraction>(`/projects/${projectId}/extract`, {
    method: "POST",
    body,
    isFormData: true,
  });
}

export async function extractFromPdf(
  projectId: string,
  file: File,
  projectName: string,
): Promise<Extraction> {
  const body = new FormData();
  body.set("file", file);
  body.set("projectName", projectName);
  return apiFetch<Extraction>(`/projects/${projectId}/extract`, {
    method: "POST",
    body,
    isFormData: true,
  });
}

/** A reply to an FR-5 "insufficient input" outcome — `text` is the detail
 * just typed, combined server-side with whatever the earlier attempt
 * already had (a pasted description, or a PDF's extracted text) rather than
 * starting over. Still one extraction, one model call; `previousExtractionId`
 * only tells the server what to combine the new text with. */
export async function continueExtraction(
  projectId: string,
  previousExtractionId: string,
  text: string,
  projectName?: string,
): Promise<Extraction> {
  const body = new FormData();
  body.set("text", text);
  body.set("previousExtractionId", previousExtractionId);
  if (projectName) body.set("projectName", projectName);
  return apiFetch<Extraction>(`/projects/${projectId}/extract`, {
    method: "POST",
    body,
    isFormData: true,
  });
}

export async function getExtraction(projectId: string, extractionId: string): Promise<Extraction> {
  return apiFetch<Extraction>(`/projects/${projectId}/extractions/${extractionId}`);
}

/** Live progress. Returns a function that stops listening. */
export function streamExtraction(
  projectId: string,
  extractionId: string,
  onUpdate: (extraction: Extraction) => void,
): () => void {
  return streamJson<Extraction>(`/projects/${projectId}/extractions/${extractionId}/events`, onUpdate);
}
