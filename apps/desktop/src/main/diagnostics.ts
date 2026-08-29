import { appendFileSync, mkdirSync } from "node:fs";
import { join } from "node:path";

const SENSITIVE_PATTERN = /(token|secret|password|api[_-]?key|authorization|cookie)/gi;

export function diagnosticsLog(name: "electron" | "preload" | "renderer" | "runtime-api", message: string): void {
  const projectRoot = process.env.CLM_PROJECT_ROOT ?? process.cwd();
  const logDir = join(projectRoot, ".runtime", "logs");
  mkdirSync(logDir, { recursive: true });
  const clean = message.replace(SENSITIVE_PATTERN, "[redacted-key]");
  appendFileSync(join(logDir, `${name}.log`), `${new Date().toISOString()} ${clean}\n`, "utf8");
}
