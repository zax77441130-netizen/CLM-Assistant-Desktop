import { describe, expect, it } from "vitest";
import { IPC_CHANNELS } from "../src/main/ipcChannels";

describe("IPC allowlist", () => {
  it("contains only explicit runtime channels", () => {
    expect(Object.values(IPC_CHANNELS).sort()).toEqual(["runtime:shutdown", "runtime:status"]);
  });
});
