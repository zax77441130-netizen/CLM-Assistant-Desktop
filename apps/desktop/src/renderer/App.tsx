import React, { useEffect, useState } from "react";
import { createRoot } from "react-dom/client";
import { Bot, ClipboardList, Settings, Workflow } from "lucide-react";
import type { RuntimeStatus } from "@clm/contracts";
import { bridgeErrorMessage, getDesktopBridge, type Approval, type RegisteredApp, type TaskResult, type Workspace } from "./desktopApiClient";
import { stateLabel, t } from "./i18n";
import "./styles.css";

type Page = "assistant" | "tasks" | "automations" | "settings";

const pages: Array<{ id: Page; label: string; icon: React.ComponentType<{ size?: number }> }> = [
  { id: "assistant", label: t("assistant"), icon: Bot },
  { id: "tasks", label: t("tasks"), icon: ClipboardList },
  { id: "automations", label: t("automations"), icon: Workflow },
  { id: "settings", label: t("settings"), icon: Settings }
];

export function App(): React.ReactElement {
  const [page, setPage] = useState<Page>("assistant");
  const [status, setStatus] = useState<RuntimeStatus | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [bridgeReady, setBridgeReady] = useState(false);

  useEffect(() => {
    const load = async () => {
      const bridge = getDesktopBridge();
      setBridgeReady(Boolean(bridge));
      if (!bridge) {
        setError(bridgeErrorMessage());
        return;
      }
      try {
        setStatus(await bridge.getRuntimeStatus());
        setError(null);
      } catch (event) {
        setError(event instanceof Error ? event.message : "本機執行核心尚未就緒，請稍後再試。");
      }
    };
    void load();
    const timer = window.setInterval(load, 2500);
    return () => window.clearInterval(timer);
  }, []);

  return (
    <main className="shell">
      <aside className="sidebar">
        <div className="brand">
          <strong>{t("appName")}</strong>
          <span>{t("phase")}</span>
        </div>
        <nav>
          {pages.map((item) => {
            const Icon = item.icon;
            return (
              <button className={page === item.id ? "active" : ""} key={item.id} onClick={() => setPage(item.id)}>
                <Icon size={18} />
                {item.label}
              </button>
            );
          })}
        </nav>
      </aside>
      <section className="content">
        <header className="topbar">
          <div>
            <h1>{pages.find((item) => item.id === page)?.label}</h1>
            <p>{t("aiNext")}</p>
          </div>
        <RuntimePill status={status} error={error} bridgeReady={bridgeReady} />
        </header>
        {error && <div className="notice error">{error}</div>}
        {page === "assistant" && <AssistantPage status={status} bridgeReady={bridgeReady} />}
        {page === "tasks" && <TasksPage />}
        {page === "automations" && <AutomationsPage />}
        {page === "settings" && <SettingsPage status={status} />}
      </section>
    </main>
  );
}

function RuntimePill({ status, error, bridgeReady }: { status: RuntimeStatus | null; error: string | null; bridgeReady: boolean }): React.ReactElement {
  if (error) {
    return <div className="pill danger">{bridgeReady ? "Runtime 錯誤" : "Bridge 未連線"}</div>;
  }
  return <div className="pill">{status?.state === "running" ? "Runtime 正常" : "Runtime 啟動中"}</div>;
}

function AssistantPage({ status, bridgeReady }: { status: RuntimeStatus | null; bridgeReady: boolean }): React.ReactElement {
  const [workspace, setWorkspace] = useState<Workspace | null>(null);
  const [taskType, setTaskType] = useState("LIST_DIRECTORY");
  const [path, setPath] = useState(".");
  const [destination, setDestination] = useState("");
  const [content, setContent] = useState("");
  const [appId, setAppId] = useState("notepad");
  const [result, setResult] = useState<TaskResult | null>(null);
  const [tasks, setTasks] = useState<TaskResult[]>([]);
  const [approvals, setApprovals] = useState<Approval[]>([]);
  const [registeredApps, setRegisteredApps] = useState<RegisteredApp[]>([]);
  const [error, setError] = useState<string | null>(null);
  const [loading, setLoading] = useState<string | null>(null);
  const ready = bridgeReady && status?.state === "running";

  const refresh = async () => {
    const bridge = getDesktopBridge();
    if (!bridge) {
      setError(bridgeErrorMessage());
      return;
    }
    setLoading("refresh");
    try {
      const [workspaceList, taskList, approvalList, apps] = await Promise.all([
        bridge.getWorkspaces(),
        bridge.getTasks(),
        bridge.getApprovals(),
        bridge.getRegisteredApps()
      ]);
      setWorkspace(workspaceList[0] ?? workspace);
      setTasks(taskList);
      setApprovals(approvalList);
      setRegisteredApps(apps.apps ?? []);
      setError(null);
    } catch (event) {
      setError(event instanceof Error ? event.message : "重新整理失敗，請查看系統診斷紀錄。");
    } finally {
      setLoading(null);
    }
  };

  useEffect(() => {
    if (ready) {
      void refresh();
    }
  }, [ready]);

  const selectWorkspace = async () => {
    const bridge = getDesktopBridge();
    if (!bridge || !ready) {
      setError("本機執行核心尚未就緒，請稍後再試。");
      return;
    }
    setError(null);
    setLoading("selectWorkspace");
    try {
      const selected = await bridge.selectWorkspace();
      if (selected && !("cancelled" in selected)) {
        setWorkspace(selected);
        await refresh();
      }
    } catch (event) {
      setError(event instanceof Error ? event.message : "選擇工作資料夾失敗。");
    } finally {
      setLoading(null);
    }
  };

  const runTask = async () => {
    const bridge = getDesktopBridge();
    if (!bridge || !ready) {
      setError("本機執行核心尚未就緒，請稍後再試。");
      return;
    }
    setError(null);
    setLoading("runTask");
    try {
      const payload = {
        task_type: taskType,
        workspace_id: needsWorkspace(taskType) ? workspace?.id : undefined,
        path,
        destination: destination || undefined,
        content: content || undefined,
        query: content || undefined,
        search_content: taskType === "SEARCH_FILES",
        app_id: taskType === "LAUNCH_REGISTERED_APP" ? appId : undefined
      };
      const nextResult = await bridge.createStructuredTask(payload);
      setResult(nextResult);
      await refresh();
    } catch (event) {
      setError(event instanceof Error ? event.message : "任務執行失敗，詳細技術資訊請查看本機 log。");
    } finally {
      setLoading(null);
    }
  };

  const decide = async (approve: boolean) => {
    const bridge = getDesktopBridge();
    if (!result?.approval_id) {
      return;
    }
    setLoading(approve ? "approve" : "reject");
    try {
      setResult(await bridge!.decideApproval(result.approval_id, approve));
      await refresh();
    } catch (event) {
      setError(event instanceof Error ? event.message : "核准流程失敗。");
    } finally {
      setLoading(null);
    }
  };

  const undo = async () => {
    const bridge = getDesktopBridge();
    if (!result?.undo_record_id) {
      return;
    }
    setLoading("undo");
    try {
      setResult(await bridge!.undoAction(result.undo_record_id));
      await refresh();
    } catch (event) {
      setError(event instanceof Error ? event.message : "Undo 失敗。");
    } finally {
      setLoading(null);
    }
  };

  return (
    <div className="grid">
      <section className="panel primary">
        <label htmlFor="task">自然語言任務</label>
        <textarea id="task" placeholder="描述你要在這台 Windows 主機完成的工作..." disabled />
        <div className="notice">{t("aiNext")}</div>
        <div className="workspace-row">
          <button disabled={!ready || loading === "selectWorkspace"} onClick={selectWorkspace}>{loading === "selectWorkspace" ? "選擇中..." : t("selectWorkspace")}</button>
          <button disabled={!ready || loading === "refresh"} onClick={refresh}>{loading === "refresh" ? "重新整理中..." : "重新整理"}</button>
          <span>{t("currentWorkspace")}: {workspace?.display_path ?? t("noWorkspace")}</span>
        </div>
      </section>
      <section className="panel">
        <h2>{t("runtime")}</h2>
        <dl>
          <dt>Bridge</dt>
          <dd>{bridgeReady ? "已連線" : "未連線"}</dd>
          <dt>IPC</dt>
          <dd>{bridgeReady ? "正常" : "錯誤"}</dd>
          <dt>Runtime</dt>
          <dd>{status?.state === "running" ? "正常" : "啟動中"}</dd>
          <dt>Host</dt>
          <dd>{status?.host ?? "pending"}</dd>
          <dt>Port</dt>
          <dd>{status?.port ?? "pending"}</dd>
          <dt>Database</dt>
          <dd>{status?.databaseReady ? "ready" : "pending"}</dd>
          <dt>Token In Renderer</dt>
          <dd>{String(status?.tokenExposedToRenderer ?? false)}</dd>
        </dl>
      </section>
      <section className="panel wide">
        <h2>{t("structuredTask")}</h2>
        <div className="form-grid">
          <select value={taskType} onChange={(event) => setTaskType(event.target.value)}>
            {["LIST_DIRECTORY", "STAT_PATH", "READ_TEXT", "SEARCH_FILES", "HASH_FILE", "FIND_DUPLICATES", "CREATE_DIRECTORY", "WRITE_NEW_TEXT", "COPY_FILE", "MOVE_FILE", "RENAME_FILE", "OVERWRITE_TEXT", "SYSTEM_INFO", "LIST_PROCESSES", "LIST_REGISTERED_APPS", "LAUNCH_REGISTERED_APP"].map((item) => (
              <option key={item} value={item}>{item}</option>
            ))}
          </select>
          <input value={path} onChange={(event) => setPath(event.target.value)} placeholder="relative/path.txt" />
          <input value={destination} onChange={(event) => setDestination(event.target.value)} placeholder="destination relative path" />
          <textarea value={content} onChange={(event) => setContent(event.target.value)} placeholder="content or search query" />
          {taskType === "LAUNCH_REGISTERED_APP" && (
            <select value={appId} onChange={(event) => setAppId(event.target.value)}>
              {(registeredApps.length > 0 ? registeredApps : [{ id: "notepad", name: "Notepad" }]).map((item) => (
                <option key={item.id} value={item.id}>{item.name}</option>
              ))}
            </select>
          )}
          <button disabled={!ready || loading === "runTask" || (needsWorkspace(taskType) && !workspace)} onClick={runTask}>{loading === "runTask" ? "執行中..." : t("runTask")}</button>
          <button disabled title="取消任務將於後續 Worker 取消機制啟用">取消任務（尚未啟用）</button>
        </div>
        {error && <div className="notice error">{t("error")}: {error}</div>}
        {result && (
          <div className="result-box">
            <strong>{t("result")}</strong>
            <p>{stateLabel(result.state)} · {result.summary}</p>
            {result.approval_id && <div className="approval-card"><strong>{t("approval")}</strong><button disabled={loading === "approve"} onClick={() => decide(true)}>{loading === "approve" ? "核准中..." : t("approve")}</button><button disabled={loading === "reject"} onClick={() => decide(false)}>{loading === "reject" ? "拒絕中..." : t("reject")}</button></div>}
            {result.undo_record_id && <button disabled={loading === "undo"} onClick={undo}>{loading === "undo" ? "復原中..." : t("undo")}</button>}
            <pre>{JSON.stringify(result.observation ?? {}, null, 2)}</pre>
          </div>
        )}
      </section>
      <section className="panel wide">
        <h2>執行時間軸</h2>
        <ol className="timeline">
          <li>Bridge：{bridgeReady ? "已連線" : "未連線"}</li>
          <li>Runtime：{status?.state === "running" ? "正常" : "啟動中"}</li>
          <li>Task：{result ? `${stateLabel(result.state)} ${result.summary ?? ""}` : "尚未建立"}</li>
          {tasks.slice(0, 5).map((task) => <li key={task.id}>{stateLabel(task.state)} · {task.title ?? task.id}</li>)}
          {approvals.slice(0, 3).map((approval) => <li key={approval.id}>核准：{approval.status} · {approval.tool_name}</li>)}
        </ol>
      </section>
    </div>
  );
}

function needsWorkspace(taskType: string): boolean {
  return !["SYSTEM_INFO", "LIST_PROCESSES", "LIST_REGISTERED_APPS", "LAUNCH_REGISTERED_APP"].includes(taskType);
}

function TasksPage(): React.ReactElement {
  return <section className="panel"><h2>任務佇列</h2><p>Task data model is ready. Mock task flow is reserved for integration validation.</p></section>;
}

function AutomationsPage(): React.ReactElement {
  return <section className="panel"><h2>自動化</h2><p>Scheduler model exists. Automation execution is not enabled in Phase 1.</p></section>;
}

function SettingsPage({ status }: { status: RuntimeStatus | null }): React.ReactElement {
  return <section className="panel"><h2>設定</h2><p>Runtime PID: {status?.pid ?? "pending"}</p><p>Session token is intentionally unavailable here.</p></section>;
}

createRoot(document.getElementById("root")!).render(<App />);
