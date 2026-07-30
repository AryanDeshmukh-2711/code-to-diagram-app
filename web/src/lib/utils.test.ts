import { describe, expect, it } from "vitest";
import { cn } from "./utils";

describe("cn", () => {
  it("merges conditional classes", () => {
    expect(cn("p-2", false && "hidden", "text-sm")).toBe("p-2 text-sm");
  });

  it("lets the later tailwind class win", () => {
    expect(cn("p-2", "p-4")).toBe("p-4");
  });
});
