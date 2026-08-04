import Link from "next/link";

import { Button } from "@/components/ui/button";
import { Card, CardContent, CardFooter, CardHeader, CardTitle } from "@/components/ui/card";

export type SessionExpiredCardProps = {
  /** Where sign-in sends the user back to once they're re-authenticated —
   * this project's own chat, so the fix for "your session expired" is not
   * also "and now you're on the home page." */
  returnTo: string;
};

/**
 * A 401, anywhere in this session, lands here instead of the hard redirect
 * `client.ts`'s default unauthorized handler would otherwise fire — see
 * ChatSession's own docstring for why that handler is overridden while this
 * component's session is mounted. Losing the transcript to an unannounced
 * navigation is the "dead conversation" the DoD names; this keeps everything
 * already said on screen and offers the one way forward.
 */
export function SessionExpiredCard({ returnTo }: SessionExpiredCardProps) {
  return (
    <Card className="max-w-md border-destructive/40">
      <CardHeader className="pb-3">
        <CardTitle className="text-base">Your session expired</CardTitle>
      </CardHeader>
      <CardContent className="text-sm text-muted-foreground">
        <p>Sign in again to keep going — nothing above is lost.</p>
      </CardContent>
      <CardFooter>
        <Button asChild size="sm">
          <Link href={`/signin?next=${encodeURIComponent(returnTo)}`}>Sign in again</Link>
        </Button>
      </CardFooter>
    </Card>
  );
}
