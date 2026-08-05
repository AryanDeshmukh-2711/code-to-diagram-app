import { useEffect, useRef, useState } from "react";
import { CheckCircle2, CircleDashed, CircleSlash, Download, Loader2, XCircle } from "lucide-react";

import { absoluteUrl, listArtefactLinks } from "@/lib/exports";
import type { Artefact, Run } from "@/lib/runs";
import { Badge } from "@/components/ui/badge";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { Progress } from "@/components/ui/progress";

export type DiagramProgressCardProps = {
  run: Run;
};

/** A run stops changing once it is pending/running no longer — that is also
 * the earliest point a signed link is guaranteed to exist for every
 * succeeded artefact, so links are fetched once here rather than re-fetched
 * on every SSE frame while diagrams are still being drawn. */
function useArtefactLinks(run: Run): Record<string, string> {
  const [links, setLinks] = useState<Record<string, string>>({});
  const fetchedFor = useRef<string | null>(null);

  useEffect(() => {
    const terminal = run.status === "succeeded" || run.status === "failed";
    if (!terminal || fetchedFor.current === run.runId) return;
    fetchedFor.current = run.runId;

    listArtefactLinks(run.runId)
      .then(({ artefacts }) => {
        setLinks(Object.fromEntries(artefacts.map((a) => [a.diagramType, absoluteUrl(a.url)])));
      })
      .catch(() => {
        // No links this run — the download column just stays empty, same as
        // any diagram that never rendered.
      });
  }, [run.runId, run.status]);

  return links;
}

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
  const anyFailed = run.artefacts.some((artefact) => artefact.status === "failed");
  const links = useArtefactLinks(run);

  return (
    <Card className="max-w-md">
      <CardHeader className="pb-3">
        <div className="flex items-center justify-between gap-2">
          <CardTitle className="text-base">Generating your diagrams</CardTitle>
          <StatusBadge status={run.status} anyFailed={anyFailed} />
        </div>
      </CardHeader>
      <CardContent className="space-y-3">
        {run.status !== "failed" ? (
          <Progress value={percent} aria-label={`${finished} of ${total} diagrams finished`} />
        ) : null}
        <ul className="space-y-1.5">
          {run.artefacts.map((artefact) => (
            <ArtefactRow
              key={artefact.diagramType}
              artefact={artefact}
              downloadUrl={links[artefact.diagramType]}
            />
          ))}
        </ul>
        {run.error ? <p className="text-xs text-destructive">{run.error}</p> : null}
      </CardContent>
    </Card>
  );
}

/**
 * A skipped diagram (FR-11: nothing in the model to draw — not an error) and
 * a failed one (a real error) must never look interchangeable at a glance.
 * Icon and colour carry that distinction, not just the label word: a failed
 * row is destructive-red with an X, a skipped row is neutral grey with a
 * slash, the same "absent, not broken" language a disabled control uses
 * elsewhere in this UI.
 */
function ArtefactRow({ artefact, downloadUrl }: { artefact: Artefact; downloadUrl?: string }) {
  return (
    <li className="flex items-center justify-between gap-2 text-sm">
      <span className="text-foreground">{artefact.title || artefact.diagramType}</span>
      <span className="flex items-center gap-1.5 text-xs">
        {artefact.carriedForward ? (
          <Badge variant="outline" className="mr-1">
            carried forward
          </Badge>
        ) : null}
        <RowStatus status={artefact.status} />
        {downloadUrl ? (
          <a
            href={downloadUrl}
            download
            aria-label={`Download ${artefact.title || artefact.diagramType}`}
            className="text-muted-foreground hover:text-foreground"
          >
            <Download className="size-3.5" />
          </a>
        ) : null}
      </span>
    </li>
  );
}

function RowStatus({ status }: { status: string }) {
  const label = STATUS_LABEL[status] ?? status;
  switch (status) {
    case "succeeded":
      return (
        <span className="flex items-center gap-1 text-emerald-700 dark:text-emerald-400">
          <CheckCircle2 className="size-3.5" />
          {label}
        </span>
      );
    case "failed":
      return (
        <span className="flex items-center gap-1 text-destructive">
          <XCircle className="size-3.5" />
          {label}
        </span>
      );
    case "skipped":
      return (
        <span className="flex items-center gap-1 text-muted-foreground">
          <CircleSlash className="size-3.5" />
          {label}
        </span>
      );
    case "running":
      return (
        <span className="flex items-center gap-1 text-muted-foreground">
          <Loader2 className="size-3.5 animate-spin" />
          {label}
        </span>
      );
    default:
      return (
        <span className="flex items-center gap-1 text-muted-foreground">
          <CircleDashed className="size-3.5" />
          {label}
        </span>
      );
  }
}

/** `run.status` alone is not enough here: FR-11's containment means a run
 * stays "succeeded" even when one diagram inside it failed (that is the
 * point — a bad diagram must not fail the other seven), so this badge has to
 * ask the artefacts directly rather than trust the top-level status word. */
function StatusBadge({ status, anyFailed }: { status: string; anyFailed: boolean }) {
  if (status === "failed") return <Badge variant="destructive">Failed</Badge>;
  if (status === "succeeded" && anyFailed) return <Badge variant="destructive">Partial</Badge>;
  if (status === "succeeded") return <Badge variant="secondary">Done</Badge>;
  return <Badge variant="outline">{STATUS_LABEL[status] ?? status}</Badge>;
}
