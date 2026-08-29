import type { RuntimeStatus } from "../main/runtimeTypes";

declare global {
  interface Window {
    clmAssistant: {
      runtimeStatus: () => Promise<RuntimeStatus | null>;
      shutdownRuntime: () => Promise<RuntimeStatus | null>;
      selectWorkspace: () => Promise<unknown | null>;
      getWorkspaces: () => Promise<unknown[]>;
      createStructuredTask: (payload: unknown) => Promise<unknown>;
      getApprovals: () => Promise<unknown[]>;
      decideApproval: (approvalId: string, approve: boolean) => Promise<unknown>;
      undoAction: (undoRecordId: string) => Promise<unknown>;
    };
  }
}

export {};
