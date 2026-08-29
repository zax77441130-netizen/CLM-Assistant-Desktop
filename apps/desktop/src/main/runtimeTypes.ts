export interface RuntimeStatus {
  host: "127.0.0.1";
  port: number;
  pid: number;
  state: "starting" | "running" | "stopping" | "stopped" | "failed";
  tokenExposedToRenderer: false;
  databaseReady: boolean;
  startedAt: string;
}
