import type { RuntimeStatus } from "@clm/contracts";
import { DESKTOP_API_METHODS, type DesktopApiMethod } from "../shared/ipcContract";

export interface Workspace {
  id: string;
  display_name: string;
  display_path: string;
  enabled: boolean;
}

export interface TaskResult {
  id: string;
  title?: string;
  state: string;
  summary?: string;
  observation?: Record<string, unknown>;
  approval_id?: string;
  undo_record_id?: string;
}

export interface Approval {
  id: string;
  task_id: string;
  action_id: string;
  tool_name: string;
  risk_level: string;
  risk_reason: string;
  status: string;
  expires_at: string;
}

export interface RegisteredApp {
  id: string;
  name: string;
}

export type DesktopBridge = {
  getRuntimeStatus: () => Promise<RuntimeStatus | null>;
  shutdownRuntime: () => Promise<RuntimeStatus | null>;
  selectWorkspace: () => Promise<Workspace | { cancelled: true } | null>;
  getWorkspaces: () => Promise<Workspace[]>;
  createStructuredTask: (payload: unknown) => Promise<TaskResult>;
  getTasks: () => Promise<TaskResult[]>;
  getTask: (taskId: string) => Promise<TaskResult>;
  getApprovals: () => Promise<Approval[]>;
  decideApproval: (approvalId: string, approve: boolean) => Promise<TaskResult>;
  undoAction: (undoRecordId: string) => Promise<TaskResult>;
  getRegisteredApps: () => Promise<{ apps: RegisteredApp[] }>;
};

export function getDesktopBridge(): DesktopBridge | null {
  const candidate = window.clmAssistant as DesktopBridge | undefined;
  if (!candidate) {
    return null;
  }
  const missing = DESKTOP_API_METHODS.filter((method: DesktopApiMethod) => typeof candidate[method] !== "function");
  return missing.length === 0 ? candidate : null;
}

export function bridgeErrorMessage(): string {
  return "桌面功能橋接未載入，無法操作本機功能。請重新啟動程式，或查看系統診斷紀錄。";
}
