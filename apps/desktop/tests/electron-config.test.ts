import { readFileSync } from "node:fs";
import { join } from "node:path";
import { describe, expect, it } from "vitest";

const mainSource = readFileSync(join(process.cwd(), "src/main/main.ts"), "utf8");

describe("Electron security configuration", () => {
  it("keeps renderer isolated from Node", () => {
    expect(mainSource).toContain("nodeIntegration: false");
    expect(mainSource).toContain("contextIsolation: true");
    expect(mainSource).toContain("sandbox: true");
  });

  it("supports headless runtime smoke mode", () => {
    expect(mainSource).toContain("CLM_ELECTRON_SMOKE");
  });
});
