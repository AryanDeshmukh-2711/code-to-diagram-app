import { describe, expect, it } from "vitest";

import { ApiError } from "./client";
import { quotaRefusal } from "./quota";

function refusalDetail(overrides: Record<string, unknown> = {}) {
  return {
    code: "project_limit",
    message: "You have 1 of 1 projects on the Free plan. Delete one you have finished with to start another, or move up a plan — everything you have made stays where it is.",
    tier: "free",
    limit: 1,
    used: 1,
    upgradeTo: "pro",
    upgradeGives: "Pro ($12/month) includes unlimited projects",
    ...overrides,
  };
}

describe("quotaRefusal", () => {
  it("reads every field off a 402's structured detail, verbatim", () => {
    const error = new ApiError(402, "ignored", "project_limit", refusalDetail());
    expect(quotaRefusal(error)).toEqual({
      code: "project_limit",
      message: refusalDetail().message,
      tier: "free",
      limit: 1,
      used: 1,
      upgradeTo: "pro",
      upgradeGives: "Pro ($12/month) includes unlimited projects",
    });
  });

  it("carries string limit/used through as-is (export_format uses strings, not counts)", () => {
    const error = new ApiError(
      402,
      "ignored",
      "export_format",
      refusalDetail({ code: "export_format", limit: "pdf", used: "docx" }),
    );
    expect(quotaRefusal(error)).toMatchObject({ limit: "pdf", used: "docx" });
  });

  it("defaults upgradeTo to null and upgradeGives to empty when there is no next tier", () => {
    const error = new ApiError(
      402,
      "ignored",
      "run_limit",
      refusalDetail({ upgradeTo: null, upgradeGives: "" }),
    );
    expect(quotaRefusal(error)).toMatchObject({ upgradeTo: null, upgradeGives: "" });
  });

  it("returns null for a non-402 ApiError", () => {
    const error = new ApiError(409, "conflict", "needs_png", { code: "needs_png", message: "x" });
    expect(quotaRefusal(error)).toBeNull();
  });

  it("returns null for a 402 whose detail isn't a quota refusal shape", () => {
    const error = new ApiError(402, "Payment required", undefined, "plain string detail");
    expect(quotaRefusal(error)).toBeNull();
  });

  it("returns null for a plain Error", () => {
    expect(quotaRefusal(new Error("boom"))).toBeNull();
  });
});
