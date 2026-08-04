import { Button } from "@/components/ui/button";
import { Card, CardContent, CardFooter, CardHeader, CardTitle } from "@/components/ui/card";

export type NeedsPngCardProps = {
  /** The API's own `needs_png` guidance — shown exactly as returned, never
   * reworded here. */
  message: string;
  busy?: boolean;
  onRenderPng: () => void;
};

/** DOCX embeds raster images; a run only ever drawn as SVG cannot supply
 * one. `onRenderPng` starts a fresh run against the same confirmed version
 * with `format: "png"` — the same generation path P-M6-8 already built,
 * asked for a different format, never a bespoke export-time render. */
export function NeedsPngCard({ message, busy = false, onRenderPng }: NeedsPngCardProps) {
  return (
    <Card className="max-w-md">
      <CardHeader className="pb-3">
        <CardTitle className="text-base">This export needs a PNG render</CardTitle>
      </CardHeader>
      <CardContent className="text-sm text-muted-foreground">
        <p>{message}</p>
      </CardContent>
      <CardFooter>
        <Button size="sm" onClick={onRenderPng} disabled={busy}>
          Render PNG
        </Button>
      </CardFooter>
    </Card>
  );
}
