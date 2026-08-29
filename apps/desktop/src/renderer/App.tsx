import React, { useEffect, useState } from "react";
import { createRoot } from "react-dom/client";
import { Bot, ClipboardList, Settings, Workflow } from "lucide-react";
import type { RuntimeStatus } from "@clm/contracts";
import { stateLabel, t } from "./i18n";
import "./styles.css";

type Page = "assistant" | "tasks" | "automations" | "settings";

const pages: Array<{ id: Page; label: string; icon: React.ComponentType<{ size?: number }> }> = [
  { id: "assistant", label: t("assistant"), icon: Bot },
  { id: "tasks", label: t("tasks"), icon: ClipboardList },
  { id: "automations", label: t("automations"), icon: Workflow },
  { id: "settings", label: t("settings"), icon: Settings }
];

interface Workspace {
  id: string;
  display_name: string;
  display_path: string;
  enabled: boolean;
}

interface TaskResult {
  id: string;
  state: string;
  summary?: string;
  observation?: Record<string, unknown>;
  approval_id?: string;
  undo_record_id?: string;
}

export function App(): React.ReactElement {
  const [page, setPage] = useState<Page>("assistant");
  const [status, setStatus] = useState<RuntimeStatus | null>(null);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    const load = async () => {
      try {
        setStatus(await window.clmAssistant.runtimeStatus());
      } catch (event) {
        setError(event instanceof Error ? event.message : "Runtime status failed");
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
          <RuntimePill status={status} error={error} />
        </header>
        {page === "assistant" && <AssistantPage status={status} />}
        {page === "tasks" && <TasksPage />}
        {page === "automations" && <AutomationsPage />}
        {page === "settings" && <SettingsPage status={status} />}
      </section>
    </main>
  );
}

function RuntimePill({ status, error }: { status: RuntimeStatus | null; error: string | null }): React.ReactElement {
  if (error) {
    return <div className="pill danger">Runtime Error</div>;
  }
  return <div className="pill">{status?.state ?? "starting"}</div>;
}

function AssistantPage({ status }: { status: RuntimeStatus | null }): React.ReactElement {
  const [workspace, setWorkspace] = useState<Workspace | null>(null);
  const [taskType, setTaskType] = useState("LIST_DIRECTORY");
  const [path, setPath] = useState(".");
  const [destination, setDestination] = useState("");
  const [content, setContent] = useState("");
  const [result, setResult] = useState<TaskResult | null>(null);
  const [error, setError] = useState<string | null>(null);

  const selectWorkspace = async () => {
    setError(null);
    const selected = (await window.clmAssistant.selectWorkspace()) as Workspace | null;
    if (selected) {
      setWorkspace(selected);
    }
  };

  const runTask = async () => {
    setError(null);
    try {
      const payload = {
        task_type: taskType,
        workspace_id: workspace?.id,
        path,
        destination: destination || undefined,
        content: content || undefined,
        query: content || undefined,
        search_content: taskType === "SEARCH_FILES"
      };
      setResult((await window.clmAssistant.createStructuredTask(payload)) as TaskResult);
    } catch {
      setError("任務執行失敗，詳細技術資訊請查看本機 log。");
    }
  };

  const decide = async (approve: boolean) => {
    if (!result?.approval_id) {
      return;
    }
    setResult((await window.clmAssistant.decideApproval(result.approval_id, approve)) as TaskResult);
  };

  const undo = async () => {
    if (!result?.undo_record_id) {
      return;
    }
    setResult((await window.clmAssistant.undoAction(result.undo_record_id)) as TaskResult);
  };

  return (
    <div className="grid">
      <section className="panel primary">
        <label htmlFor="task">自然語言任務</label>
        <textarea id="task" placeholder="描述你要在這台 Windows 主機完成的工作..." disabled />
        <div className="notice">{t("aiNext")}</div>
        <div className="workspace-row">
          <button onClick={selectWorkspace}>{t("selectWorkspace")}</button>
          <span>{t("currentWorkspace")}: {workspace?.display_path ?? t("noWorkspace")}</span>
        </div>
      </section>
      <section className="panel">
        <h2>{t("runtime")}</h2>
        <dl>
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
            {["LIST_DIRECTORY", "STAT_PATH", "READ_TEXT", "SEARCH_FILES", "HASH_FILE", "FIND_DUPLICATES", "CREATE_DIRECTORY", "WRITE_NEW_TEXT", "COPY_FILE", "MOVE_FILE", "RENAME_FILE", "OVERWRITE_TEXT"].map((item) => (
              <option key={item} value={item}>{item}</option>
            ))}
          </select>
          <input value={path} onChange={(event) => setPath(event.target.value)} placeholder="relative/path.txt" />
          <input value={destination} onChange={(event) => setDestination(event.target.value)} placeholder="destination relative path" />
          <textarea value={content} onChange={(event) => setContent(event.target.value)} placeholder="content or search query" />
          <button disabled={!workspace} onClick={runTask}>{t("runTask")}</button>
        </div>
        {error && <div className="notice error">{t("error")}: {error}</div>}
        {result && (
          <div className="result-box">
            <strong>{t("result")}</strong>
            <p>{stateLabel(result.state)} · {result.summary}</p>
            {result.approval_id && <div className="approval-card"><strong>{t("approval")}</strong><button onClick={() => decide(true)}>{t("approve")}</button><button onClick={() => decide(false)}>{t("reject")}</button></div>}
            {result.undo_record_id && <button onClick={undo}>{t("undo")}</button>}
            <pre>{JSON.stringify(result.observation ?? {}, null, 2)}</pre>
          </div>
        )}
      </section>
      <section className="panel wide">
        <h2>執行時間軸</h2>
        <ol className="timeline">
          <li>Runtime process launched by Electron Main.</li>
          <li>Session token retained outside Renderer.</li>
          <li>SQLite schema initialized.</li>
        </ol>
      </section>
    </div>
  );
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
