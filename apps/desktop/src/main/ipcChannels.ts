export const IPC_CHANNELS = {
  runtimeStatus: "runtime:status",
  runtimeShutdown: "runtime:shutdown"
} as const;

export type IpcChannel = (typeof IPC_CHANNELS)[keyof typeof IPC_CHANNELS];
