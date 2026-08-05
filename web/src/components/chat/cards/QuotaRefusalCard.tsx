import type { QuotaRefusal } from "@/lib/quota";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Card, CardContent, CardFooter, CardHeader, CardTitle } from "@/components/ui/card";

export type QuotaRefusalCardProps = {
  refusal: QuotaRefusal;
  /** Set only when this refusal came from starting a run — needed to retry. */
  cpmVersionId?: string;
  busy?: boolean;
  /** Starts a fresh run against `cpmVersionId` in the format the tier
   * actually allows (`refusal.limit`). Only ever offered for a
   * `diagram_format` refusal — there is no equivalent one-click fix for
   * project_limit, run_limit, export_format, or template_not_in_tier. */
  onRetryFormat?: (cpmVersionId: string, format: string) => void;
};

/**
 * A 402 quota refusal, rendered field-for-field off the API's own
 * `QuotaRefusal` — never paraphrased through an LLM call, and never folded
 * into a narration bubble as if it were assistant prose (the Watch For,
 * verbatim: routing this through the same model used for tone-consistent
 * narration is exactly the shortcut that reintroduced copy drift before).
 * `message` is shown exactly as the backend wrote it; tier, the used/limit
 * pair, and the upgrade note are each read straight off `refusal`, not
 * recomputed from it.
 */
export function QuotaRefusalCard({ refusal, cpmVersionId, busy = false, onRetryFormat }: QuotaRefusalCardProps) {
  const hasUsage = refusal.limit !== null && refusal.used !== null;
  const canRetryFormat =
    refusal.code === "diagram_format" &&
    cpmVersionId !== undefined &&
    typeof refusal.limit === "string" &&
    onRetryFormat !== undefined;

  return (
    <Card className="max-w-md border-destructive/40">
      <CardHeader className="pb-3">
        <div className="flex items-center justify-between gap-2">
          <CardTitle className="text-base">Plan limit reached</CardTitle>
          <Badge variant="outline">{refusal.tier}</Badge>
        </div>
      </CardHeader>
      <CardContent className="space-y-2 text-sm">
        <p>{refusal.message}</p>
        {hasUsage ? (
          // `used`/`limit` are a count for project_limit/run_limit ("1", "2")
          // and a category for diagram_format/export_format/template_not_in_tier
          // ("svg", "png") — labeled stats read correctly either way; a sentence
          // built around them ("svg of png") would not.
          <div className="flex gap-4 text-xs text-muted-foreground">
            <span>
              You: <span className="font-medium text-foreground">{refusal.used}</span>
            </span>
            <span>
              Plan allows: <span className="font-medium text-foreground">{refusal.limit}</span>
            </span>
          </div>
        ) : null}
        {refusal.upgradeTo ? (
          <p className="text-xs text-muted-foreground">{refusal.upgradeGives}</p>
        ) : null}
      </CardContent>
      {canRetryFormat ? (
        <CardFooter>
          <Button
            size="sm"
            disabled={busy}
            onClick={() => onRetryFormat(cpmVersionId, refusal.limit as string)}
          >
            Generate as {(refusal.limit as string).toUpperCase()}
          </Button>
        </CardFooter>
      ) : null}
    </Card>
  );
}
