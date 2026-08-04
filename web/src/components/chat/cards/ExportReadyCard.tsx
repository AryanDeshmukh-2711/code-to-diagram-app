import type { ExportResult } from "@/lib/exports";
import { absoluteUrl } from "@/lib/exports";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Card, CardContent, CardFooter, CardHeader, CardTitle } from "@/components/ui/card";

export type ExportReadyCardProps = {
  export: ExportResult;
};

function humanBytes(bytes: number | null): string | null {
  if (bytes === null) return null;
  if (bytes < 1024) return `${bytes} B`;
  return `${(bytes / 1024).toFixed(0)} KB`;
}

/** An export's state, fully formed the moment it renders — pending, failed,
 * or ready with a real signed link, never a partial document. */
export function ExportReadyCard({ export: result }: ExportReadyCardProps) {
  const size = humanBytes(result.bytes);

  return (
    <Card className="max-w-md">
      <CardHeader className="pb-3">
        <div className="flex items-center justify-between gap-2">
          <CardTitle className="text-base">
            {result.status === "succeeded" ? "Your document is ready" : "Preparing your document"}
          </CardTitle>
          <Badge variant={result.status === "succeeded" ? "secondary" : "outline"}>
            {result.format.toUpperCase()}
          </Badge>
        </div>
      </CardHeader>
      <CardContent className="text-sm text-muted-foreground">
        {result.status === "failed" ? (
          <p className="text-destructive">{result.error ?? "The export failed."}</p>
        ) : result.status === "succeeded" ? (
          <p>{size ? `${size} · ready to download` : "Ready to download"}</p>
        ) : (
          <p>Assembling the document — this only takes a moment.</p>
        )}
      </CardContent>
      {result.status === "succeeded" && result.url ? (
        <CardFooter>
          <Button asChild>
            <a href={absoluteUrl(result.url)} download>
              Download
            </a>
          </Button>
        </CardFooter>
      ) : null}
    </Card>
  );
}
