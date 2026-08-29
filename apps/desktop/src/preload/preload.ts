import { contextBridge, ipcRenderer } from "electron";
import { IPC_CHANNELS } from "../main/ipc.js";
import type { RuntimeStatus } from "../main/runtimeTypes.js";

const api = {
  runtimeStatus: (): Promise<RuntimeStatus | null> => ipcRenderer.invoke(IPC_CHANNELS.runtimeStatus),
  shutdownRuntime: (): Promise<RuntimeStatus | null> => ipcRenderer.invoke(IPC_CHANNELS.runtimeShutdown),
  selectWorkspace: () => ipcRenderer.invoke(IPC_CHANNELS.selectWorkspace),
  getWorkspaces: () => ipcRenderer.invoke(IPC_CHANNELS.getWorkspaces),
  createStructuredTask: (payload: unknown) => ipcRenderer.invoke(IPC_CHANNELS.createStructuredTask, payload),
  getApprovals: () => ipcRenderer.invoke(IPC_CHANNELS.getApprovals),
  decideApproval: (approvalId: string, approve: boolean) => ipcRenderer.invoke(IPC_CHANNELS.decideApproval, { approvalId, approve }),
  undoAction: (undoRecordId: string) => ipcRenderer.invoke(IPC_CHANNELS.undoAction, undoRecordId)
};

contextBridge.exposeInMainWorld("clmAssistant", api);
