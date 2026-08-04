import { apiFetch, streamJson } from "@/lib/client";

export type ChatEdit = {
  editId: string;
  projectId: string;
  status: string;
  outcome: string | null;
  appliedOp: string | null;
  summary: string | null;
  referencesUpdated: number | null;
  clarifyQuestion: string | null;
  reason: string | null;
  error: string | null;
};

/** 202: queues parsing and returns immediately — the model never runs in this
 * request (C-4). */
export async function sendChatMessage(projectId: string, message: string): Promise<ChatEdit> {
  return apiFetch<ChatEdit>(`/projects/${projectId}/chat`, { method: "POST", body: { message } });
}

export async function getChatEdit(projectId: string, editId: string): Promise<ChatEdit> {
  return apiFetch<ChatEdit>(`/projects/${projectId}/chat/${editId}`);
}

/** Live progress. Returns a function that stops listening. */
export function streamChatEdit(
  projectId: string,
  editId: string,
  onUpdate: (edit: ChatEdit) => void,
): () => void {
  return streamJson<ChatEdit>(`/projects/${projectId}/chat/${editId}/events`, onUpdate);
}
