import { describe, expect, it } from "vitest";
import { DESKTOP_API_METHODS } from "../src/shared/ipcContract";

describe("preload security contract", () => {
  it("does not expose token reads or API key reads", () => {
    expect(DESKTOP_API_METHODS.some((name) => name.toLowerCase().includes("token"))).toBe(false);
    expect(DESKTOP_API_METHODS).not.toContain("getProviderKey" as never);
    expect(DESKTOP_API_METHODS.filter((name) => name.toLowerCase().includes("key")).sort()).toEqual([
      "deleteProviderKey",
      "saveProviderKey"
    ]);
  });
});
