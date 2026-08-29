import { describe, expect, it } from "vitest";
import { createSessionToken } from "../src/main/security";

describe("session token", () => {
  it("generates a high-entropy hex token", () => {
    const token = createSessionToken();
    expect(token).toMatch(/^[a-f0-9]{64}$/);
  });
});
