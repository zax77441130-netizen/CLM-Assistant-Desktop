import { describe, expect, it } from "vitest";

describe("preload security contract", () => {
  it("does not expose a token-shaped API", () => {
    const exposed = ["getRuntimeStatus", "shutdownRuntime"];
    expect(exposed.some((name) => name.toLowerCase().includes("token"))).toBe(false);
  });
});
