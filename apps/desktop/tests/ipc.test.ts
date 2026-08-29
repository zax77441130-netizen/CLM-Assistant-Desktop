import { describe, expect, it } from "vitest";
import { IPC_CHANNELS } from "../src/main/ipcChannels";

describe("IPC allowlist", () => {
  it("contains only explicit safe channels", () => {
    expect(Object.values(IPC_CHANNELS).sort()).toEqual([
      "approval:decide",
      "approval:list",
      "runtime:shutdown",
      "runtime:status",
      "task:createStructured",
      "undo:apply",
      "workspace:list",
      "workspace:select"
    ]);
  });

  it("does not expose generic or raw execution channels", () => {
    const channels = Object.values(IPC_CHANNELS).join(" ");
    expect(channels).not.toMatch(/generic|raw|command|executeRawTool|runCommand/i);
  });
});
