export const DESKTOP_API_CONTRACT = {
  getRuntimeStatus: "runtime:getStatus",
  shutdownRuntime: "runtime:shutdown",
  selectWorkspace: "workspace:select",
  getWorkspaces: "workspace:list",
  createStructuredTask: "task:createStructured",
  getTasks: "task:list",
  getTask: "task:get",
  getApprovals: "approval:list",
  decideApproval: "approval:decide",
  undoAction: "undo:apply",
  getRegisteredApps: "host:registeredApps",
  preloadReady: "diagnostics:preloadReady"
} as const;

export const DESKTOP_API_METHODS = [
  "getRuntimeStatus",
  "shutdownRuntime",
  "selectWorkspace",
  "getWorkspaces",
  "createStructuredTask",
  "getTasks",
  "getTask",
  "getApprovals",
  "decideApproval",
  "undoAction",
  "getRegisteredApps"
] as const;

export type DesktopApiMethod = (typeof DESKTOP_API_METHODS)[number];
export type IpcChannel = (typeof DESKTOP_API_CONTRACT)[keyof typeof DESKTOP_API_CONTRACT];
