import { describe, expect, it } from "vitest";
import { createSessionToken } from "../src/main/security";
import { safeRuntimeErrorMessage } from "../src/main/runtimeManager";

describe("session token", () => {
  it("generates a high-entropy hex token", () => {
    const token = createSessionToken();
    expect(token).toMatch(/^[a-f0-9]{64}$/);
  });
});

describe("runtime API error boundary", () => {
  it("uses structured safe messages instead of raw internal failures", () => {
    const body = JSON.stringify({
      error: {
        code: "DATABASE_MIGRATION_REQUIRED",
        message: "本機資料庫需要更新，請重新啟動程式；若問題持續，請查看系統診斷紀錄。",
        correlationId: "corr-1"
      }
    });
    const message = safeRuntimeErrorMessage(body, 500);
    expect(message).toContain("本機資料庫需要更新");
    expect(message).toContain("corr-1");
    expect(message).not.toMatch(/SELECT|SQLAlchemy|sqlalche\\.me|sqlite/i);
  });

  it("hides unstructured HTTP bodies from the renderer", () => {
    const message = safeRuntimeErrorMessage(
      "(sqlite3.OperationalError) no such column: undo_records.created_at SELECT undo_records.created_at FROM undo_records https://sqlalche.me/e/20/e3q8",
      500
    );
    expect(message).toContain("本機執行核心暫時無法完成請求");
    expect(message).not.toMatch(/undo_records|SELECT|sqlalche\\.me|sqlite/i);
  });
});
