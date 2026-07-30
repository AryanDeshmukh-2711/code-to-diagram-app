const API_BASE_URL = process.env.NEXT_PUBLIC_API_BASE_URL ?? "http://localhost:8000";

export type DependencyStatus = {
  name: "postgres" | "redis" | "plantuml";
  ok: boolean;
  latency_ms: number;
  error: string | null;
};

export type HealthReport = {
  status: "ok" | "degraded";
  dependencies: DependencyStatus[];
};

export async function fetchHealth(): Promise<HealthReport> {
  // 503 is a valid, meaningful response here — it carries the per-dependency
  // detail — so it is parsed rather than thrown on.
  const response = await fetch(`${API_BASE_URL}/health`, { cache: "no-store" });
  return (await response.json()) as HealthReport;
}
