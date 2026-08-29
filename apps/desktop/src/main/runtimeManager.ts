import { ChildProcess, spawn } from "node:child_process";
import { existsSync, mkdirSync, readFileSync, rmSync, writeFileSync } from "node:fs";
import { dirname, join, resolve } from "node:path";
import { app } from "electron";
import { createSessionToken } from "./security.js";
import type { RuntimeStatus } from "./runtimeTypes.js";

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

export function createDefaultRuntimeManager(): RuntimeManager {
  const projectRoot = resolve(process.env.CLM_PROJECT_ROOT ?? process.cwd());
  return new RuntimeManager({
    projectRoot,
    dataDir: join(app.getPath("userData"), "runtime"),
    resourceDir: process.resourcesPath
  });
}
