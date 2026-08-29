import { contextBridge, ipcRenderer } from "electron";
import { IPC_CHANNELS } from "../main/ipc.js";
import type { RuntimeStatus } from "../main/runtimeTypes.js";

const api = {
  runtimeStatus: (): Promise<RuntimeStatus | null> => ipcRenderer.invoke(IPC_CHANNELS.runtimeStatus),
  shutdownRuntime: (): Promise<RuntimeStatus | null> => ipcRenderer.invoke(IPC_CHANNELS.runtimeShutdown)
};

contextBridge.exposeInMainWorld("clmAssistant", api);
