import type { RuntimeStatus } from "../main/runtimeTypes";

declare global {
  interface Window {
    clmAssistant: {
      getRuntimeStatus: () => Promise<RuntimeStatus | null>;
      shutdownRuntime: () => Promise<RuntimeStatus | null>;
      selectWorkspace: () => Promise<unknown | null>;
      getWorkspaces: () => Promise<unknown[]>;
      createStructuredTask: (payload: unknown) => Promise<unknown>;
      getTasks: () => Promise<unknown[]>;
      getTask: (taskId: string) => Promise<unknown>;
      getApprovals: () => Promise<unknown[]>;
      decideApproval: (approvalId: string, approve: boolean) => Promise<unknown>;
      undoAction: (undoRecordId: string) => Promise<unknown>;
      getRegisteredApps: () => Promise<{ apps: unknown[] }>;
    };
  }
}

export {};
