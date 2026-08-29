import { contextBridge, ipcRenderer } from "electron";
import type { RuntimeStatus } from "@clm/contracts";
import { IPC_CHANNELS } from "../main/ipc.js";

const api = {
  runtimeStatus: (): Promise<RuntimeStatus | null> => ipcRenderer.invoke(IPC_CHANNELS.runtimeStatus),
  shutdownRuntime: (): Promise<RuntimeStatus | null> => ipcRenderer.invoke(IPC_CHANNELS.runtimeShutdown)
};

contextBridge.exposeInMainWorld("clmAssistant", api);
