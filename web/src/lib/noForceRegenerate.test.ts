/**
 * DoD, pinned: there is no "do it anyway" affordance that forces a redraw
 * when nothing changed. Not a runtime check — RegenerateInput simply has no
 * force-shaped field, so there is nothing for any caller to set — but
 * pinned here the same way the backend pins its own "no bypass" guarantees
 * (api/tests convention), so a force flag added later "to make the UI feel
 * more responsive" (the Watch For, verbatim) fails a test before it ships.
 */

import { readFileSync } from "node:fs";
import path from "node:path";
import { fileURLToPath } from "node:url";
import { describe, expect, it } from "vitest";

const HERE = path.dirname(fileURLToPath(import.meta.url));
const SRC = path.resolve(HERE, "..");

function read(relativePath: string): string {
  return readFileSync(path.join(SRC, relativePath), "utf-8");
}

describe("no force-regenerate affordance exists", () => {
  it("RegenerateInput's own type has no force-shaped field", () => {
    const source = read("lib/runs.ts");
    const match = source.match(/export type RegenerateInput = \{[\s\S]*?\n\};/);
    expect(match).not.toBeNull();
    expect(match![0].toLowerCase()).not.toContain("force");
  });

  it("the regenerate() call itself never grows a force parameter", () => {
    const source = read("lib/runs.ts");
    const match = source.match(/export async function regenerate\([\s\S]*?\n\}/);
    expect(match).not.toBeNull();
    expect(match![0].toLowerCase()).not.toContain("force");
  });

  it("ChatSession's wiring never mentions forcing a regeneration", () => {
    const source = read("components/chat/ChatSession.tsx");
    expect(source.toLowerCase()).not.toContain("force");
  });
});
