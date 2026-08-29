import { readFileSync } from "node:fs";
import { join } from "node:path";
import { describe, expect, it } from "vitest";
import { IPC_CHANNELS } from "../src/main/ipcChannels";
import { DESKTOP_API_METHODS } from "../src/shared/ipcContract";

const preloadSource = readFileSync(join(process.cwd(), "src/preload/preload.ts"), "utf8");
const mainIpcSource = readFileSync(join(process.cwd(), "src/main/ipc.ts"), "utf8");
const globalSource = readFileSync(join(process.cwd(), "src/preload/global.d.ts"), "utf8");
const rendererClientSource = readFileSync(join(process.cwd(), "src/renderer/desktopApiClient.ts"), "utf8");

describe("IPC allowlist", () => {
  it("contains only explicit safe channels", () => {
    expect(Object.values(IPC_CHANNELS).sort()).toEqual([
      "approval:decide",
      "approval:list",
      "assistant:cancelTask",
      "assistant:createTask",
      "diagnostics:preloadReady",
      "host:registeredApps",
      "provider:deleteKey",
      "provider:getSettings",
      "provider:saveKey",
      "provider:test",
      "provider:updateSettings",
      "runtime:getStatus",
      "runtime:shutdown",
      "task:createStructured",
      "task:get",
      "task:list",
      "undo:apply",
      "workspace:list",
      "workspace:select"
    ]);
  });

  it("does not expose generic or raw execution channels", () => {
    const channels = Object.values(IPC_CHANNELS).join(" ");
    const sources = [channels, preloadSource, mainIpcSource, globalSource, rendererClientSource].join(" ");
    expect(sources).not.toMatch(/genericInvoke|executeRawTool|runArbitraryCommand|sendUnvalidatedAbsolutePath/i);
  });

  it("keeps renderer, preload, IPC handlers, and global types in parity", () => {
    for (const method of DESKTOP_API_METHODS) {
      expect(rendererClientSource).toContain(`${method}`);
      expect(preloadSource).toContain(`${method}`);
      expect(globalSource).toContain(`${method}`);
      expect(mainIpcSource).toContain(`IPC_CHANNELS.${method}`);
    }
  });

  it("loads preload from the pure IPC contract instead of main-process modules", () => {
    expect(preloadSource).toContain("../shared/ipcContract.js");
    expect(preloadSource).not.toContain("../main/ipc.js");
  });
});
