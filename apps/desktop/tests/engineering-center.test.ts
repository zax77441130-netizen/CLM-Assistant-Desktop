import { readFileSync } from "node:fs";
import { join } from "node:path";
import { describe, expect, it } from "vitest";

const engineeringPage = readFileSync(join(process.cwd(), "src/renderer/EngineeringPage.tsx"), "utf8");
const mainIpc = readFileSync(join(process.cwd(), "src/main/ipc.ts"), "utf8");
const preload = readFileSync(join(process.cwd(), "src/preload/preload.ts"), "utf8");

describe("Engineering Center security contract", () => {
  it("offers only fixed test and build actions without a command input", () => {
    expect(engineeringPage).toContain('runCommand("test")');
    expect(engineeringPage).toContain('runCommand("build")');
    expect(engineeringPage).toContain("每次執行都必須再次核准");
    expect(engineeringPage).not.toMatch(/<textarea|<input/i);
  });

  it("converts the explicit IPC request into a fixed structured task", () => {
    expect(mainIpc).toContain('task_type: "ENGINEERING_RUN"');
    expect(mainIpc).toContain('commandId !== "test" && commandId !== "build"');
    expect(mainIpc).toContain("timeout_seconds: 60");
    expect(mainIpc).toContain("encodeURIComponent(validated)");
    expect(mainIpc).not.toMatch(/rawCommand|executablePath|workingDirectory|shell:\s*true/i);
  });

  it("keeps Engineering methods explicit across the preload boundary", () => {
    expect(preload).toContain("getEngineeringProjectContext");
    expect(preload).toContain("runEngineeringCommand");
    expect(preload).not.toMatch(/runCommand:\s*\(payload:\s*unknown\)/i);
  });
});
