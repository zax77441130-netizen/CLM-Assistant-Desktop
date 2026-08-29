import { BrowserWindow, dialog, ipcMain, type OpenDialogOptions } from "electron";
import type { RuntimeManager } from "./runtimeManager.js";
import { IPC_CHANNELS } from "./ipcChannels.js";
import { diagnosticsLog } from "./diagnostics.js";

export { IPC_CHANNELS };

export function registerIpc(runtime: RuntimeManager): void {
  ipcMain.on(IPC_CHANNELS.preloadReady, (_event, payload) => diagnosticsLog("preload", `bridge-ready ${JSON.stringify(payload)}`));
  ipcMain.handle(IPC_CHANNELS.getRuntimeStatus, () => runtime.getStatus());
  ipcMain.handle(IPC_CHANNELS.shutdownRuntime, async () => {
    await runtime.stop();
    return runtime.getStatus();
  });
  ipcMain.handle(IPC_CHANNELS.selectWorkspace, async () => {
    const focused = BrowserWindow.getFocusedWindow();
    const options: OpenDialogOptions = {
      properties: ["openDirectory"],
      title: "選擇工作資料夾"
    };
    const result = focused ? await dialog.showOpenDialog(focused, options) : await dialog.showOpenDialog(options);
    if (result.canceled || result.filePaths.length === 0) {
      return { cancelled: true };
    }
    const rootPath = result.filePaths[0];
    return runtime.runtimeRequest("/api/workspaces", {
      method: "POST",
      body: JSON.stringify({ root_path: rootPath })
    });
  });
  ipcMain.handle(IPC_CHANNELS.getWorkspaces, () => runtime.runtimeRequest("/api/workspaces"));
  ipcMain.handle(IPC_CHANNELS.createStructuredTask, (_event, payload: unknown) =>
    runtime.runtimeRequest("/api/tasks/structured", { method: "POST", body: JSON.stringify(payload) })
  );
  ipcMain.handle(IPC_CHANNELS.createAssistantTask, (_event, payload: unknown) =>
    runtime.runtimeRequest("/api/assistant/tasks", { method: "POST", body: JSON.stringify(payload) })
  );
  ipcMain.handle(IPC_CHANNELS.cancelAssistantTask, (_event, taskId: string) =>
    runtime.runtimeRequest(`/api/assistant/tasks/${encodeURIComponent(taskId)}/cancel`, { method: "POST" })
  );
  ipcMain.handle(IPC_CHANNELS.getTasks, () => runtime.runtimeRequest("/api/tasks"));
  ipcMain.handle(IPC_CHANNELS.getTask, (_event, taskId: string) => runtime.runtimeRequest(`/api/tasks/${encodeURIComponent(taskId)}`));
  ipcMain.handle(IPC_CHANNELS.getApprovals, () => runtime.runtimeRequest("/api/approvals"));
  ipcMain.handle(IPC_CHANNELS.decideApproval, (_event, payload: { approvalId: string; approve: boolean }) =>
    runtime.runtimeRequest(`/api/approvals/${payload.approvalId}/decision`, {
      method: "POST",
      body: JSON.stringify({ approve: payload.approve })
    })
  );
  ipcMain.handle(IPC_CHANNELS.undoAction, (_event, undoRecordId: string) =>
    runtime.runtimeRequest(`/api/undo/${undoRecordId}`, { method: "POST" })
  );
  ipcMain.handle(IPC_CHANNELS.getRegisteredApps, () => runtime.runtimeRequest("/api/host/registered-apps"));
  ipcMain.handle(IPC_CHANNELS.getProviderSettings, () => runtime.runtimeRequest("/api/provider/settings"));
  ipcMain.handle(IPC_CHANNELS.updateProviderSettings, (_event, payload: unknown) =>
    runtime.runtimeRequest("/api/provider/settings", { method: "PATCH", body: JSON.stringify(payload) })
  );
  ipcMain.handle(IPC_CHANNELS.saveProviderKey, (_event, payload: unknown) =>
    runtime.runtimeRequest("/api/provider/openai-key", { method: "PUT", body: JSON.stringify(payload) })
  );
  ipcMain.handle(IPC_CHANNELS.deleteProviderKey, () => runtime.runtimeRequest("/api/provider/openai-key", { method: "DELETE" }));
  ipcMain.handle(IPC_CHANNELS.testProvider, () => runtime.runtimeRequest("/api/provider/test", { method: "POST" }));
}
