import { ChildProcess, spawn } from "node:child_process";
import { randomUUID } from "node:crypto";
import { existsSync, mkdirSync, readFileSync, rmSync, writeFileSync } from "node:fs";
import { dirname, join, resolve } from "node:path";
import { app } from "electron";
import { createSessionToken } from "./security.js";
import type { RuntimeStatus } from "./runtimeTypes.js";
import { diagnosticsLog } from "./diagnostics.js";

export interface RuntimeManagerOptions {
  projectRoot: string;
  dataDir: string;
  resourceDir: string;
  stateFile?: string;
}

export class RuntimeManager {
  private child: ChildProcess | null = null;
  private readonly token = createSessionToken();
  private status: RuntimeStatus | null = null;
  private readonly stateFile: string;

  constructor(private readonly options: RuntimeManagerOptions) {
    this.stateFile = options.stateFile ?? join(options.dataDir, "runtime-state.json");
  }

  getStatus(): RuntimeStatus | null {
    return this.status;
  }

  getTokenForMainOnly(): string {
    return this.token;
  }

  async runtimeRequest<T>(path: string, init: RequestInit = {}): Promise<T> {
    if (!this.status || this.status.state !== "running") {
      throw new Error("Agent Runtime is not running.");
    }
    const requestId = randomUUID();
    const method = init.method ?? "GET";
    diagnosticsLog("runtime-api", `${requestId} ${method} ${path}`);
    let response: Response;
    try {
      response = await fetch(`http://127.0.0.1:${this.status.port}${path}`, {
        ...init,
        headers: {
          "Content-Type": "application/json",
          "X-Desktop-Token": this.token,
          "X-Request-ID": requestId,
          ...(init.headers ?? {})
        }
      });
    } catch (error) {
      diagnosticsLog("runtime-api", `${requestId} fetch-error ${error instanceof Error ? error.message : String(error)}`);
      throw new Error("本機執行核心連線失敗，請重新啟動 Runtime。");
    }
    if (!response.ok) {
      const body = await response.text();
      diagnosticsLog("runtime-api", `${requestId} http-${response.status} ${body.slice(0, 500)}`);
      throw new Error(safeRuntimeErrorMessage(body, response.status));
    }
    diagnosticsLog("runtime-api", `${requestId} ok ${response.status}`);
    return (await response.json()) as T;
  }

  async runtimeRequestWithoutJson(path: string, init: RequestInit = {}): Promise<void> {
    await this.runtimeRequest(path, {
      ...init,
      headers: init.headers
    });
  }

  async start(): Promise<RuntimeStatus> {
    mkdirSync(this.options.dataDir, { recursive: true });
    mkdirSync(dirname(this.stateFile), { recursive: true });
    rmSync(this.stateFile, { force: true });

    const runtimeEntry = join(this.options.projectRoot, "services", "agent_runtime");
    const env = {
      ...process.env,
      CLM_DESKTOP_TOKEN: this.token,
      CLM_DATA_DIR: this.options.dataDir,
      CLM_RESOURCE_DIR: this.options.resourceDir,
      CLM_RUNTIME_STATE_FILE: this.stateFile
    };

    const command = this.resolvePythonCommand();
    this.child = spawn(command.executable, [...command.args, "-m", "app.main"], {
      cwd: runtimeEntry,
      env,
      windowsHide: true,
      stdio: ["ignore", "pipe", "pipe"]
    });
    this.child.stdout?.on("data", (chunk) => diagnosticsLog("electron", `runtime-stdout ${String(chunk).trim()}`));
    this.child.stderr?.on("data", (chunk) => diagnosticsLog("electron", `runtime-stderr ${String(chunk).trim()}`));

    writeFileSync(join(this.options.dataDir, "runtime.pid"), String(this.child.pid ?? ""), "utf8");
    this.child.once("exit", () => {
      if (this.status?.state !== "stopped") {
        this.status = this.status ? { ...this.status, state: "failed" } : null;
      }
    });

    this.status = await this.waitForStateFile();
    return this.status;
  }

  async stop(): Promise<void> {
    if (!this.child) {
      return;
    }
    this.status = this.status ? { ...this.status, state: "stopping" } : null;
    this.child.kill();
    await new Promise<void>((resolveStop) => {
      const timer = setTimeout(() => resolveStop(), 3000);
      this.child?.once("exit", () => {
        clearTimeout(timer);
        resolveStop();
      });
    });
    this.status = this.status ? { ...this.status, state: "stopped" } : null;
    this.child = null;
  }

  private resolvePythonCommand(): { executable: string; args: string[] } {
    const localPython = resolve(this.options.projectRoot, ".venv-win", "Scripts", "python.exe");
    if (existsSync(localPython)) {
      return { executable: localPython, args: [] };
    }
    return { executable: "py", args: ["-3.12"] };
  }

  private async waitForStateFile(): Promise<RuntimeStatus> {
    const started = Date.now();
    while (Date.now() - started < 15000) {
      if (existsSync(this.stateFile)) {
        const parsed = JSON.parse(readFileSync(this.stateFile, "utf8")) as RuntimeStatus;
        if (parsed.host !== "127.0.0.1" || parsed.tokenExposedToRenderer !== false) {
          throw new Error("Runtime security boundary failed");
        }
        return parsed;
      }
      await new Promise((resolveWait) => setTimeout(resolveWait, 100));
    }
    throw new Error("Agent Runtime did not start within 15 seconds");
  }
}

interface RuntimeErrorPayload {
  error?: {
    message?: string;
    correlationId?: string;
  };
}

export function safeRuntimeErrorMessage(body: string, status: number): string {
  try {
    const parsed = JSON.parse(body) as RuntimeErrorPayload;
    if (parsed.error?.message) {
      const suffix = parsed.error.correlationId ? `（診斷代碼：${parsed.error.correlationId}）` : "";
      return `${parsed.error.message}${suffix}`;
    }
  } catch {
    diagnosticsLog("runtime-api", `safe-error-parse-failed status=${status}`);
  }
  return `本機執行核心暫時無法完成請求，請重新整理或重新啟動 Runtime。`;
}

export function createDefaultRuntimeManager(): RuntimeManager {
  const projectRoot = resolve(process.env.CLM_PROJECT_ROOT ?? process.cwd());
  return new RuntimeManager({
    projectRoot,
    dataDir: join(app.getPath("userData"), "runtime"),
    resourceDir: process.resourcesPath
  });
}
