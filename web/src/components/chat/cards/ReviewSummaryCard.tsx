import Link from "next/link";

import type { Review } from "@/lib/review";
import { Badge } from "@/components/ui/badge";
import { Card, CardContent, CardFooter, CardHeader, CardTitle } from "@/components/ui/card";

export type ReviewSummaryCardProps = {
  review: Review;
};

/** A snapshot of the model in review — fully formed the moment it renders.
 * Re-rendered wholesale with a fresh `review` after each edit; it never
 * updates one field at a time. */
export function ReviewSummaryCard({ review }: ReviewSummaryCardProps) {
  const problems = review.issues.length;

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
      {review.lastEdit ? (
        <CardContent className="pt-0 text-xs text-muted-foreground">{review.lastEdit}</CardContent>
      ) : null}
      <CardFooter>
        <Link
          href={`/review/${review.projectId}`}
          className="text-sm font-medium text-primary underline-offset-4 hover:underline"
        >
          Open the review screen
        </Link>
      </CardFooter>
    </Card>
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
