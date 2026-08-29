export const IPC_CHANNELS = {
  runtimeStatus: "runtime:status",
  runtimeShutdown: "runtime:shutdown",
  selectWorkspace: "workspace:select",
  getWorkspaces: "workspace:list",
  createStructuredTask: "task:createStructured",
  getApprovals: "approval:list",
  decideApproval: "approval:decide",
  undoAction: "undo:apply"
} as const;

export type IpcChannel = (typeof IPC_CHANNELS)[keyof typeof IPC_CHANNELS];
