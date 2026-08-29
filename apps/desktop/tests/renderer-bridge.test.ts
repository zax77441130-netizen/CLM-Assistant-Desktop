import { describe, expect, it } from "vitest";
import { bridgeErrorMessage, getDesktopBridge } from "../src/renderer/desktopApiClient";

describe("renderer desktop bridge handling", () => {
  it("returns null and a fatal Chinese error when the bridge is missing", () => {
    Reflect.deleteProperty(window, "clmAssistant");
    expect(getDesktopBridge()).toBeNull();
    expect(bridgeErrorMessage()).toContain("桌面功能橋接未載入");
  });

  it("accepts the complete explicit bridge surface", () => {
    Object.defineProperty(window, "clmAssistant", {
      configurable: true,
      value: {
        getRuntimeStatus: async () => null,
        shutdownRuntime: async () => null,
        selectWorkspace: async () => ({ cancelled: true }),
        getWorkspaces: async () => [],
        createStructuredTask: async () => ({ id: "task", state: "COMPLETED" }),
        createAssistantTask: async () => ({ id: "task", state: "COMPLETED", providerMode: "local", progress: [] }),
        cancelAssistantTask: async () => ({ id: "task", state: "CANCELLED", providerMode: "local", progress: [] }),
        getTasks: async () => [],
        getTask: async () => ({ id: "task", state: "COMPLETED" }),
        getApprovals: async () => [],
        decideApproval: async () => ({ id: "task", state: "BLOCKED" }),
        undoAction: async () => ({ id: "task", state: "COMPLETED" }),
        getRegisteredApps: async () => ({ apps: [] }),
        getProviderSettings: async () => ({ mode: "local", model: "gpt-5.6-luna", apiKeyConfigured: false }),
        updateProviderSettings: async () => ({ mode: "local", model: "gpt-5.6-luna", apiKeyConfigured: false }),
        saveProviderKey: async () => ({ mode: "openai", model: "gpt-5.6-luna", apiKeyConfigured: true }),
        deleteProviderKey: async () => ({ mode: "local", model: "gpt-5.6-luna", apiKeyConfigured: false }),
        testProvider: async () => ({ ok: true, message: "本機指令模式可用。" })
      }
    });
    expect(getDesktopBridge()).not.toBeNull();
  });
});
