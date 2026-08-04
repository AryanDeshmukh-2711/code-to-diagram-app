import Link from "next/link";

import type { Issue, Review } from "@/lib/review";
import { Badge } from "@/components/ui/badge";
import { Card, CardContent, CardFooter, CardHeader, CardTitle } from "@/components/ui/card";

export type ReviewSummaryCardProps = {
  review: Review;
};

const MAX_ISSUES_SHOWN = 4;

/** A snapshot of the model in review — fully formed the moment it renders.
 * Every number and name here is read straight off `review`, which is always
 * `GET .../review`'s own response (P-M6-5's DoD): no count is recomputed
 * from the entity list, no issue is reworded, nothing here can drift from
 * what the backend would show on the full review screen. Re-rendered
 * wholesale with a fresh `review` after each edit; it never updates one
 * field at a time. */
export function ReviewSummaryCard({ review }: ReviewSummaryCardProps) {
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

      <CardFooter>
        <Link
          href={`/review/${review.projectId}`}
          className="text-sm font-medium text-primary underline-offset-4 hover:underline"
        >
          Open the review screen for every attribute
        </Link>
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
