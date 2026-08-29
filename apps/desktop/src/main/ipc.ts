import { ipcMain } from "electron";
import type { RuntimeManager } from "./runtimeManager.js";
import { IPC_CHANNELS } from "./ipcChannels.js";

export { IPC_CHANNELS };

export function registerIpc(runtime: RuntimeManager): void {
  ipcMain.handle(IPC_CHANNELS.runtimeStatus, () => runtime.getStatus());
  ipcMain.handle(IPC_CHANNELS.runtimeShutdown, async () => {
    await runtime.stop();
    return runtime.getStatus();
  });
}
