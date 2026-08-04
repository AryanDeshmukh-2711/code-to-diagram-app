import Link from "next/link";

import type { ConfirmedVersion } from "@/components/chat/types";
import type { Issue, Review } from "@/lib/review";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Card, CardContent, CardFooter, CardHeader, CardTitle } from "@/components/ui/card";

export type ReviewSummaryCardProps = {
  review: Review;
  /** Omitted entirely by the sandbox and anywhere else confirming should not
   * be possible. Confirming is this one button — see the module docstring
   * for why nothing else may cause it. */
  onConfirm?: () => void;
  confirming?: boolean;
  confirmedVersion?: ConfirmedVersion | null;
};

const MAX_ISSUES_SHOWN = 4;

/** A snapshot of the model in review — fully formed the moment it renders.
 * Every number and name here is read straight off `review`, which is always
 * `GET .../review`'s own response (P-M6-5's DoD): no count is recomputed
 * from the entity list, no issue is reworded, nothing here can drift from
 * what the backend would show on the full review screen. Re-rendered
 * wholesale with a fresh `review` after each edit; it never updates one
 * field at a time.
 *
 * FR-6/FR-7: this button is the only way `onConfirm` ever fires. No text
 * typed into the composer reaches it — P-M6-2's parser has no "confirm" op
 * to recognise in the first place (see
 * shared/tests/test_confirm_is_not_chat_parseable.py), so there is no
 * message this card could receive that would click it for the user.
 */
export function ReviewSummaryCard({
  review,
  onConfirm,
  confirming = false,
  confirmedVersion = null,
}: ReviewSummaryCardProps) {
  const problems = review.issues.length;
  const entities = review.draft.entities ?? [];

  return (
    <Card className="max-w-md">
      <CardHeader className="pb-3">
        <div className="flex items-center justify-between gap-2">
          <CardTitle className="text-base">{review.projectName}</CardTitle>
          {review.confirmable ? (
            <Badge variant="secondary">Ready to confirm</Badge>
          ) : (
            <Badge variant="destructive">
              {problems} thing{problems === 1 ? "" : "s"} to fix
            </Badge>
          )}
        </div>
      </CardHeader>
      <CardContent className="grid grid-cols-4 gap-3 text-center text-sm">
        <Count label="things" value={review.counts.entities} />
        <Count label="connections" value={review.counts.relationships} />
        <Count label="people" value={review.counts.actors} />
        <Count label="use cases" value={review.counts.useCases} />
      </CardContent>

      {entities.length > 0 ? (
        <CardContent className="pt-0">
          <div className="flex flex-wrap gap-1.5">
            {entities.map((entity) => (
              <Badge key={entity.id} variant="outline" className="font-normal">
                {entity.name}
              </Badge>
            ))}
          </div>
        </CardContent>
      ) : null}

      {problems > 0 ? (
        <CardContent className="pt-0">
          <IssueList issues={review.issues} />
        </CardContent>
      ) : null}

      {review.lastEdit ? (
        <CardContent className="pt-0 text-xs text-muted-foreground">{review.lastEdit}</CardContent>
      ) : null}

      <CardFooter className="flex flex-wrap items-center justify-between gap-3">
        <Link
          href={`/review/${review.projectId}`}
          className="text-sm font-medium text-primary underline-offset-4 hover:underline"
        >
          Open the review screen for every attribute
        </Link>

        {onConfirm ? (
          confirmedVersion ? (
            <Badge variant="secondary">Confirmed · v{confirmedVersion.version}</Badge>
          ) : (
            <Button
              size="sm"
              onClick={onConfirm}
              // Same gate the review screen's own confirm button uses:
              // disabled whenever GET .../review says confirmable is false.
              disabled={confirming || !review.confirmable}
            >
              {confirming ? "Confirming…" : "Confirm"}
            </Button>
          )
        ) : null}
      </CardFooter>
    </Card>
  );
}

function IssueList({ issues }: { issues: Issue[] }) {
  const shown = issues.slice(0, MAX_ISSUES_SHOWN);
  const remaining = issues.length - shown.length;
  return (
    <ul className="space-y-1">
      {shown.map((issue) => (
        <li key={issue.path + issue.code} className="text-xs text-destructive">
          {issue.explanation}
        </li>
      ))}
      {remaining > 0 ? (
        <li className="text-xs text-muted-foreground">
          +{remaining} more — see the full review screen.
        </li>
      ) : null}
    </ul>
  );
}

function Count({ label, value }: { label: string; value: number }) {
  return (
    <div>
      <p className="text-lg font-semibold tracking-tight">{value}</p>
      <p className="text-xs text-muted-foreground">{label}</p>
    </div>
  );
}
