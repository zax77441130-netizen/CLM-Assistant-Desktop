import { describe, expect, it } from "vitest";
import { stateLabel, t } from "../src/renderer/i18n";

describe("Traditional Chinese UI text", () => {
  it("maps task states to Chinese labels", () => {
    expect(stateLabel("RECEIVED")).toBe("已接收");
    expect(stateLabel("RUNNING")).toBe("執行中");
    expect(stateLabel("WAITING_APPROVAL")).toBe("等待核准");
    expect(stateLabel("COMPLETED")).toBe("已完成");
    expect(stateLabel("BLOCKED")).toBe("已阻擋");
  });

  it("labels next phase AI intake honestly", () => {
    expect(t("aiNext")).toContain("下一階段");
  });
});
