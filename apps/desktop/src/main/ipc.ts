import { BrowserWindow, dialog, ipcMain, type OpenDialogOptions } from "electron";
import type { RuntimeManager } from "./runtimeManager.js";
import { IPC_CHANNELS } from "./ipcChannels.js";

export { IPC_CHANNELS };

export function registerIpc(runtime: RuntimeManager): void {
  ipcMain.handle(IPC_CHANNELS.runtimeStatus, () => runtime.getStatus());
  ipcMain.handle(IPC_CHANNELS.runtimeShutdown, async () => {
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
      return null;
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
}
