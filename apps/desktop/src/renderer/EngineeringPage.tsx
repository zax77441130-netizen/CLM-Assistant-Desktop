import React, { useEffect, useState } from "react";
import type { RuntimeStatus } from "@clm/contracts";
import { FolderOpen, GitBranch, Hammer, Play, RefreshCw, ShieldCheck } from "lucide-react";
import {
  bridgeErrorMessage,
  getDesktopBridge,
  type Approval,
  type EngineeringProjectContext,
  type TaskResult,
  type Workspace
} from "./desktopApiClient";
import { stateLabel } from "./i18n";

const ACTIVE_WORKSPACE_KEY = "clm.activeWorkspaceId";

export function EngineeringPage({
  status,
  bridgeReady
}: {
  status: RuntimeStatus | null;
  bridgeReady: boolean;
}): React.ReactElement {
  const [workspace, setWorkspace] = useState<Workspace | null>(null);
  const [context, setContext] = useState<EngineeringProjectContext | null>(null);
  const [task, setTask] = useState<TaskResult | null>(null);
  const [approval, setApproval] = useState<Approval | null>(null);
  const [loading, setLoading] = useState<string | null>(null);
  const [error, setError] = useState<string | null>(null);
  const ready = bridgeReady && status?.state === "running";

  const loadContext = async (target: Workspace): Promise<void> => {
    const bridge = getDesktopBridge();
    if (!bridge) {
      setError(bridgeErrorMessage());
      return;
    }
    setLoading("context");
    try {
      setContext(await bridge.getEngineeringProjectContext(target.id));
      setTask(null);
      setApproval(null);
      setError(null);
    } catch (event) {
      setContext(null);
      setError(safeEngineeringError(event, "無法讀取工程專案資訊。"));
    } finally {
      setLoading(null);
    }
  };

  const loadWorkspace = async (): Promise<void> => {
    const bridge = getDesktopBridge();
    if (!bridge) {
      setError(bridgeErrorMessage());
      return;
    }
    try {
      const workspaces = await bridge.getWorkspaces();
      const activeId = window.localStorage.getItem(ACTIVE_WORKSPACE_KEY);
      const selected = workspaces.find((item) => item.id === activeId) ?? workspaces[0] ?? null;
      setWorkspace(selected);
      if (selected) {
        await loadContext(selected);
      } else {
        setContext(null);
      }
    } catch (event) {
      setError(safeEngineeringError(event, "無法讀取工作區。"));
    }
  };

  useEffect(() => {
    if (ready) {
      void loadWorkspace();
    }
  }, [ready]);

  const selectWorkspace = async (): Promise<void> => {
    const bridge = getDesktopBridge();
    if (!bridge || !ready) {
      setError("助理尚未就緒，請稍後再試。");
      return;
    }
    setLoading("workspace");
    try {
      const selected = await bridge.selectWorkspace();
      if (selected && !("cancelled" in selected)) {
        setWorkspace(selected);
        window.localStorage.setItem(ACTIVE_WORKSPACE_KEY, selected.id);
        await loadContext(selected);
      }
      setError(null);
    } catch (event) {
      setError(safeEngineeringError(event, "選擇工程專案失敗。"));
    } finally {
      setLoading(null);
    }
  };

  const runCommand = async (commandId: "test" | "build"): Promise<void> => {
    const bridge = getDesktopBridge();
    if (!bridge || !workspace || !ready) {
      setError("請先選擇可用的工程工作區。");
      return;
    }
    setLoading(commandId);
    setTask(null);
    setApproval(null);
    setError(null);
    try {
      const nextTask = await bridge.runEngineeringCommand(workspace.id, commandId);
      setTask(nextTask);
      if (nextTask.approval_id) {
        const approvals = await bridge.getApprovals();
        setApproval(approvals.find((item) => item.id === nextTask.approval_id) ?? null);
      }
    } catch (event) {
      setError(safeEngineeringError(event, "無法建立工程執行任務。"));
    } finally {
      setLoading(null);
    }
  };

  const decide = async (approve: boolean): Promise<void> => {
    const bridge = getDesktopBridge();
    if (!bridge || !task?.approval_id) {
      return;
    }
    setLoading(approve ? "approve" : "reject");
    setError(null);
    try {
      const decided = await bridge.decideApproval(task.approval_id, approve);
      setTask(decided);
      setApproval(null);
    } catch (event) {
      setError(safeEngineeringError(event, "工程任務核准失敗。"));
    } finally {
      setLoading(null);
    }
  };

  const supportsTest = context?.testCommands.includes(".\\scripts\\test_windows.ps1") ?? false;
  const supportsBuild = context?.buildCommands.includes(".\\scripts\\build_desktop.ps1") ?? false;
  const output = typeof task?.observation?.output === "string" ? task.observation.output : null;
  const gitLabel = context?.git.detected
    ? (context.git.branch ?? "detached") + (context.git.commit ? " · " + context.git.commit.slice(0, 8) : "")
    : "未偵測到";
  const scanLabel = context
    ? String(context.scan.fileCount) + " 個檔案 · " + String(context.scan.directoryCount) + " 個資料夾" + (context.scan.truncated ? " · 已達安全上限" : "")
    : "";

  return (
    <div className="engineering-layout">
      <section className="panel engineering-project">
        <div className="panel-heading">
          <div>
            <span className="eyebrow">目前工程工作區</span>
            <h2>{workspace?.display_name ?? "尚未選擇專案"}</h2>
            <p className="muted workspace-path">{workspace?.display_path ?? "請先選擇程式專案資料夾。"}</p>
          </div>
          <div className="engineering-heading-actions">
            <button disabled={!ready || loading === "workspace"} onClick={selectWorkspace}>
              <FolderOpen size={17} />
              選擇專案
            </button>
            <button disabled={!workspace || loading === "context"} onClick={() => workspace && void loadContext(workspace)}>
              <RefreshCw size={17} />
              重新掃描
            </button>
          </div>
        </div>
        {error && <div className="notice error">{error}</div>}
        {!workspace && <p className="muted">工程中心只會讀取你明確選擇並授權的工作區。</p>}
        {workspace && !context && loading === "context" && <p className="muted">正在安全掃描專案結構…</p>}
        {context && (
          <div className="engineering-summary">
            <InfoCard title="技術棧" value={context.stacks.join("、") || "尚未辨識"} />
            <InfoCard title="專案入口" value={context.entrypoints.slice(0, 3).join("、") || "尚未辨識"} />
            <InfoCard title="Git" value={gitLabel} />
            <InfoCard title="掃描範圍" value={scanLabel} />
          </div>
        )}
      </section>

      <section className="panel engineering-actions">
        <div className="panel-heading">
          <div>
            <span className="eyebrow">受控執行</span>
            <h2>測試與建置</h2>
          </div>
          <ShieldCheck size={22} />
        </div>
        <p className="muted">只允許專案內固定的 Windows 驗證腳本。每次執行都必須再次核准。</p>
        <div className="engineering-command-grid">
          <button className="primary-action" disabled={!ready || !supportsTest || loading !== null} onClick={() => runCommand("test")}>
            <Play size={18} />
            {loading === "test" ? "準備中" : "執行完整測試"}
          </button>
          <button disabled={!ready || !supportsBuild || loading !== null} onClick={() => runCommand("build")}>
            <Hammer size={18} />
            {loading === "build" ? "準備中" : "執行桌面建置"}
          </button>
        </div>
        {context && !supportsTest && !supportsBuild && (
          <div className="notice">此工作區沒有受支援的 Windows 測試或建置腳本，因此不會開放執行。</div>
        )}
      </section>

      <section className="panel engineering-result">
        <div className="panel-heading">
          <div>
            <span className="eyebrow">執行狀態</span>
            <h2>{task ? stateLabel(task.state) : "尚未執行"}</h2>
          </div>
          {context?.git.detected && <GitBranch size={22} />}
        </div>
        {approval && task?.approval_id && (
          <div className="approval-card engineering-approval">
            <div>
              <strong>需要明確核准</strong>
              <span>{approval.risk_reason}</span>
              <small>核准有效期限：{new Date(approval.expires_at).toLocaleString("zh-TW")}</small>
            </div>
            <button className="primary-action" disabled={loading !== null} onClick={() => decide(true)}>
              核准並執行
            </button>
            <button disabled={loading !== null} onClick={() => decide(false)}>
              拒絕
            </button>
          </div>
        )}
        {loading === "approve" && <p className="muted">正在執行受控工程腳本，請稍候…</p>}
        {task && <p className="result-text">{engineeringTaskSummary(task)}</p>}
        {output && <pre className="preview engineering-output">{output}</pre>}
        {!task && <p className="muted">測試或建置結果會顯示在這裡，完整任務也會保留於任務中心。</p>}
      </section>
    </div>
  );
}

function InfoCard({ title, value }: { title: string; value: string }): React.ReactElement {
  return (
    <div className="engineering-info-card">
      <span>{title}</span>
      <strong>{value}</strong>
    </div>
  );
}

function engineeringTaskSummary(task: TaskResult): string {
  if (task.state === "WAITING_APPROVAL") {
    return "工程任務已建立，等待你的明確核准。";
  }
  if (task.state === "COMPLETED") {
    return "工程腳本執行完成，結果已保留於任務中心。";
  }
  if (task.state === "FAILED") {
    return "工程腳本執行失敗，請查看下方輸出。";
  }
  if (task.state === "BLOCKED") {
    return "工程任務已拒絕、失效或被安全政策阻擋。";
  }
  return task.summary ?? "工程任務處理中。";
}

function safeEngineeringError(_event: unknown, fallback: string): string {
  return fallback;
}
