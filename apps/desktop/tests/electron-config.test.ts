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

  it("derives preload path from the built main module location", () => {
    expect(mainSource).toContain("import.meta.url");
    expect(mainSource).toContain("distRoot");
    expect(mainSource).toContain("preload.cjs");
    expect(mainSource).not.toContain('app.getAppPath(), "dist", "preload"');
  });
});
