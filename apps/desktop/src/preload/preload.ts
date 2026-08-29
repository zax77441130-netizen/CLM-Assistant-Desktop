import { contextBridge, ipcRenderer } from "electron";
import { DESKTOP_API_CONTRACT } from "../shared/ipcContract.js";
import type { RuntimeStatus } from "../main/runtimeTypes.js";

const api = {
  getRuntimeStatus: (): Promise<RuntimeStatus | null> => ipcRenderer.invoke(DESKTOP_API_CONTRACT.getRuntimeStatus),
  shutdownRuntime: (): Promise<RuntimeStatus | null> => ipcRenderer.invoke(DESKTOP_API_CONTRACT.shutdownRuntime),
  selectWorkspace: () => ipcRenderer.invoke(DESKTOP_API_CONTRACT.selectWorkspace),
  getWorkspaces: () => ipcRenderer.invoke(DESKTOP_API_CONTRACT.getWorkspaces),
  createStructuredTask: (payload: unknown) => ipcRenderer.invoke(DESKTOP_API_CONTRACT.createStructuredTask, payload),
  getTasks: () => ipcRenderer.invoke(DESKTOP_API_CONTRACT.getTasks),
  getTask: (taskId: string) => ipcRenderer.invoke(DESKTOP_API_CONTRACT.getTask, taskId),
  getApprovals: () => ipcRenderer.invoke(DESKTOP_API_CONTRACT.getApprovals),
  decideApproval: (approvalId: string, approve: boolean) => ipcRenderer.invoke(DESKTOP_API_CONTRACT.decideApproval, { approvalId, approve }),
  undoAction: (undoRecordId: string) => ipcRenderer.invoke(DESKTOP_API_CONTRACT.undoAction, undoRecordId),
  getRegisteredApps: () => ipcRenderer.invoke(DESKTOP_API_CONTRACT.getRegisteredApps)
};

contextBridge.exposeInMainWorld("clmAssistant", api);
ipcRenderer.send(DESKTOP_API_CONTRACT.preloadReady, { ready: true });
