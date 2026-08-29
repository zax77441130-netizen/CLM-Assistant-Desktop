export type TaskState =
  | "RECEIVED"
  | "ANALYZING"
  | "NEEDS_INPUT"
  | "PLANNED"
  | "RUNNING"
  | "WAITING_APPROVAL"
  | "VERIFYING"
  | "COMPLETED"
  | "FAILED"
  | "CANCELLED"
  | "BLOCKED";

export interface RuntimeStatus {
  host: "127.0.0.1";
  port: number;
  pid: number;
  state: "starting" | "running" | "stopping" | "stopped" | "failed";
  tokenExposedToRenderer: false;
  databaseReady: boolean;
  startedAt: string;
}

export interface TaskSummary {
  id: string;
  title: string;
  state: TaskState;
  createdAt: string;
}
