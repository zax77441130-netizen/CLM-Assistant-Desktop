import type { TaskState } from "@clm/contracts";

const zh = {
  appName: "CLM Assistant",
  phase: "Foundation / Development",
  aiNext: "AI 任務理解將於下一階段啟用",
  assistant: "助理",
  tasks: "任務",
  automations: "自動化",
  settings: "設定",
  selectWorkspace: "選擇工作資料夾",
  currentWorkspace: "目前工作區",
  noWorkspace: "尚未選擇",
  structuredTask: "結構化檔案任務",
  runTask: "執行任務",
  approve: "核准",
  reject: "拒絕",
  undo: "Undo",
  result: "結果摘要",
  approval: "核准卡片",
  error: "錯誤",
  runtime: "Runtime",
  tokenUnavailable: "Session token 不會提供給 Renderer",
  state: {
    RECEIVED: "已接收",
    ANALYZING: "分析中",
    NEEDS_INPUT: "需要補充",
    PLANNED: "已規劃",
    RUNNING: "執行中",
    WAITING_APPROVAL: "等待核准",
    VERIFYING: "驗證中",
    COMPLETED: "已完成",
    FAILED: "失敗",
    CANCELLED: "已取消",
    BLOCKED: "已阻擋"
  } satisfies Record<TaskState, string>
};

export function t(key: keyof typeof zh): string {
  const value = zh[key];
  return typeof value === "string" ? value : key;
}

export function stateLabel(state: TaskState | string | undefined): string {
  if (!state) {
    return "未知";
  }
  return zh.state[state as TaskState] ?? state;
}
