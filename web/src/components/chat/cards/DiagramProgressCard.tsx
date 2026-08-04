import type { Artefact, Run } from "@/lib/runs";
import { Badge } from "@/components/ui/badge";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { Progress } from "@/components/ui/progress";

export type DiagramProgressCardProps = {
  run: Run;
};

const STATUS_LABEL: Record<string, string> = {
  pending: "Queued",
  running: "Drawing",
  succeeded: "Done",
  failed: "Failed",
  skipped: "Skipped",
};

/** A run's state, fully formed the moment it renders. The caller re-renders
 * this with a fresh `run` on every SSE frame; it never shows a diagram
 * mid-render or a count ticking up field by field. */
export function DiagramProgressCard({ run }: DiagramProgressCardProps) {
  const finished = run.artefacts.filter(
    (artefact) => artefact.status === "succeeded" || artefact.status === "failed",
  ).length;
  const total = run.artefacts.length || run.requestedTypes.length;
  const percent = total > 0 ? Math.round((finished / total) * 100) : 0;

  return (
    <Card className="max-w-md">
      <CardHeader className="pb-3">
        <div className="flex items-center justify-between gap-2">
          <CardTitle className="text-base">Generating your diagrams</CardTitle>
          <StatusBadge status={run.status} />
        </div>
      </CardHeader>
      <CardContent className="space-y-3">
        {run.status !== "failed" ? (
          <Progress value={percent} aria-label={`${finished} of ${total} diagrams finished`} />
        ) : null}
        <ul className="space-y-1.5">
          {run.artefacts.map((artefact) => (
            <ArtefactRow key={artefact.diagramType} artefact={artefact} />
          ))}
        </ul>
        {run.error ? <p className="text-xs text-destructive">{run.error}</p> : null}
      </CardContent>
    </Card>
  );
}

function ArtefactRow({ artefact }: { artefact: Artefact }) {
  return (
    <li className="flex items-center justify-between gap-2 text-sm">
      <span className="text-foreground">{artefact.title || artefact.diagramType}</span>
      <span className="flex items-center gap-2 text-xs text-muted-foreground">
        {artefact.carriedForward ? <Badge variant="outline">carried forward</Badge> : null}
        {STATUS_LABEL[artefact.status] ?? artefact.status}
      </span>
    </li>
  );
}

function StatusBadge({ status }: { status: string }) {
  if (status === "succeeded") return <Badge variant="secondary">Done</Badge>;
  if (status === "failed") return <Badge variant="destructive">Failed</Badge>;
  return <Badge variant="outline">{STATUS_LABEL[status] ?? status}</Badge>;
}
