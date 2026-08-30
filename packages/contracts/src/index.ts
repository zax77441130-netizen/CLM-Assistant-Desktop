export type TaskState =
  | "CREATED"
  | "PLANNING"
  | "WAITING_CLARIFICATION"
  | "RECEIVED"
  | "ANALYZING"
  | "NEEDS_INPUT"
  | "PLANNED"
  | "QUEUED"
  | "RUNNING"
  | "RETRYING"
  | "CANCELLING"
  | "WAITING_APPROVAL"
  | "VERIFYING"
  | "COMPLETED"
  | "FAILED"
  | "CANCELLED"
  | "BLOCKED"
  | "NEEDS_REVIEW";

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
