import React, { useEffect, useState } from "react";
import { createRoot } from "react-dom/client";
import { Bot, ClipboardList, FolderOpen, Play, RotateCcw, Settings, ShieldCheck, Square, Trash2, Workflow } from "lucide-react";
import type { RuntimeStatus } from "@clm/contracts";
import {
  bridgeErrorMessage,
  getDesktopBridge,
  type Approval,
  type AssistantTaskResult,
  type ProviderSettings,
  type RegisteredApp,
  type TaskResult,
  type Workspace
} from "./desktopApiClient";
import { stateLabel, t } from "./i18n";
import "./styles.css";

type Page = "assistant" | "tasks" | "automations" | "settings";

const pages: Array<{ id: Page; label: string; icon: React.ComponentType<{ size?: number }> }> = [
  { id: "assistant", label: "助理", icon: Bot },
  { id: "tasks", label: "任務", icon: ClipboardList },
  { id: "automations", label: "自動化", icon: Workflow },
  { id: "settings", label: "設定", icon: Settings }
];

const examples = ["列出目前工作區的檔案", "讀取 example.txt", "找出重複檔案", "建立資料夾 測試建立"];

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
        await Promise.all([bridge.getTasks(), bridge.getApprovals(), bridge.getRegisteredApps()]);
        setError(null);
      } catch (event) {
        setError(safeError(event, "本機執行核心尚未就緒，請稍後再試。"));
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
          <span>Windows 本機助理</span>
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
            <p>用中文描述要完成的本機工作，助理會先規劃再安全執行。</p>
          </div>
          <RuntimePill status={status} error={error} bridgeReady={bridgeReady} />
        </header>
        {error && <div className="notice error">{error}</div>}
        {page === "assistant" && <AssistantPage status={status} bridgeReady={bridgeReady} />}
        {page === "tasks" && <TasksPage />}
        {page === "automations" && <AutomationsPage />}
        {page === "settings" && <SettingsPage status={status} bridgeReady={bridgeReady} />}
      </section>
    </main>
  );
}

function RuntimePill({ status, error, bridgeReady }: { status: RuntimeStatus | null; error: string | null; bridgeReady: boolean }): React.ReactElement {
  if (error) {
    return <div className="pill danger">{bridgeReady ? "助理暫時無法執行" : "桌面橋接未連線"}</div>;
  }
  return <div className="pill">{status?.state === "running" ? "助理可用" : "助理啟動中"}</div>;
}

function AssistantPage({ status, bridgeReady }: { status: RuntimeStatus | null; bridgeReady: boolean }): React.ReactElement {
  const [workspace, setWorkspace] = useState<Workspace | null>(null);
  const [message, setMessage] = useState("列出目前工作區的檔案");
  const [result, setResult] = useState<AssistantTaskResult | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [loading, setLoading] = useState<string | null>(null);
  const [detailsOpen, setDetailsOpen] = useState(false);
  const ready = bridgeReady && status?.state === "running";

  const refreshWorkspace = async () => {
    const bridge = getDesktopBridge();
    if (!bridge) {
      setError(bridgeErrorMessage());
      return;
    }
    const workspaces = await bridge.getWorkspaces();
    setWorkspace(workspaces[0] ?? null);
  };

  useEffect(() => {
    if (ready) {
      void refreshWorkspace();
    }
  }, [ready]);

  const selectWorkspace = async () => {
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
      }
      setError(null);
    } catch (event) {
      setError(safeError(event, "選擇工作區失敗。"));
    } finally {
      setLoading(null);
    }
  };

  const runAssistantTask = async () => {
    const bridge = getDesktopBridge();
    if (!bridge || !ready) {
      setError("助理尚未就緒，請稍後再試。");
      return;
    }
    setLoading("run");
    setError(null);
    setResult(null);
    try {
      const next = await bridge.createAssistantTask({ message, workspace_id: workspace?.id });
      setResult(next);
    } catch (event) {
      setError(safeError(event, "任務執行失敗，請查看系統診斷紀錄。"));
    } finally {
      setLoading(null);
    }
  };

  const cancelTask = async () => {
    const bridge = getDesktopBridge();
    if (!bridge || !result) {
      return;
    }
    setLoading("cancel");
    try {
      setResult(await bridge.cancelAssistantTask(result.id));
    } catch (event) {
      setError(safeError(event, "取消任務失敗。"));
    } finally {
      setLoading(null);
    }
  };

  const decide = async (approve: boolean) => {
    const bridge = getDesktopBridge();
    if (!bridge || !result?.approval_id) {
      return;
    }
    setLoading(approve ? "approve" : "reject");
    try {
      const next = await bridge.decideApproval(result.approval_id, approve);
      setResult({
        ...result,
        state: next.state,
        resultText: next.summary ?? (approve ? "已核准並完成操作。" : "已拒絕，檔案保持不變。"),
        summary: next.summary,
        approval_id: next.approval_id,
        undo_record_id: next.undo_record_id,
        technicalDetails: next.observation
      });
    } catch (event) {
      setError(safeError(event, "核准流程失敗。"));
    } finally {
      setLoading(null);
    }
  };

  const undo = async () => {
    const bridge = getDesktopBridge();
    if (!bridge || !result?.undo_record_id) {
      return;
    }
    setLoading("undo");
    try {
      const next = await bridge.undoAction(result.undo_record_id);
      setResult({ ...result, state: next.state, resultText: next.summary ?? "已復原上一步。", undo_record_id: next.undo_record_id });
    } catch (event) {
      setError(safeError(event, "復原失敗。"));
    } finally {
      setLoading(null);
    }
  };

  return (
    <div className="assistant-layout">
      <section className="assistant-compose">
        <div className="workspace-strip">
          <div>
            <span className="eyebrow">目前工作區</span>
            <strong>{workspace?.display_path ?? "尚未選擇"}</strong>
          </div>
          <button className="icon-text" disabled={!ready || loading === "workspace"} onClick={selectWorkspace}>
            <FolderOpen size={18} />
            {loading === "workspace" ? "選擇中" : "選擇工作區"}
          </button>
        </div>
        <label htmlFor="assistant-message">你想讓助理完成什麼？</label>
        <textarea id="assistant-message" value={message} onChange={(event) => setMessage(event.target.value)} placeholder="例如：列出目前工作區的檔案" />
        <div className="example-row">
          {examples.map((example) => (
            <button key={example} onClick={() => setMessage(example)}>{example}</button>
          ))}
        </div>
        <div className="action-row">
          <button className="primary-action" disabled={!ready || loading === "run" || !message.trim()} onClick={runAssistantTask}>
            <Play size={18} />
            {loading === "run" ? "執行中" : "執行任務"}
          </button>
          <button disabled={!result || loading === "cancel"} onClick={cancelTask}>
            <Square size={16} />
            停止任務
          </button>
          <button disabled={!result?.undo_record_id || loading === "undo"} onClick={undo}>
            <RotateCcw size={16} />
            復原上一步
          </button>
        </div>
        {error && <div className="notice error">{error}</div>}
      </section>

      <section className="assistant-status">
        <h2>助理狀態</h2>
        <div className="status-list">
          <span><ShieldCheck size={16} /> {ready ? "可執行本機任務" : "啟動中"}</span>
          <span>本機指令模式</span>
          <span>{workspace ? "工作區已選擇" : "請先選擇工作區"}</span>
        </div>
      </section>

      <section className="assistant-output">
        <h2>任務計畫</h2>
        {result?.plan ? (
          <ol className="plan-list">
            {result.plan.steps.length > 0 ? result.plan.steps.map((step, index) => (
              <li key={`${step.title}-${index}`}>
                <strong>{step.title}</strong>
                <span>{step.reason}</span>
              </li>
            )) : <li>{result.plan.clarificationQuestion}</li>}
          </ol>
        ) : (
          <p className="muted">送出任務後，助理會先產生安全計畫。</p>
        )}
      </section>

      <section className="assistant-output">
        <h2>執行進度</h2>
        {result?.progress.length ? <ol className="timeline">{result.progress.map((item) => <li key={item}>{item}</li>)}</ol> : <p className="muted">尚未開始執行。</p>}
      </section>

      <section className="assistant-output wide">
        <h2>結果</h2>
        {result ? (
          <>
            <p className="result-text">{result.resultText ?? result.summary}</p>
            {result.observationPreview && <pre className="preview">{result.observationPreview}</pre>}
            {result.approval_id && (
              <div className="approval-card">
                <strong>需要核准</strong>
                <span>這個操作可能改變既有內容，請確認後再執行。</span>
                <button disabled={loading === "approve"} onClick={() => decide(true)}>核准</button>
                <button disabled={loading === "reject"} onClick={() => decide(false)}>拒絕</button>
              </div>
            )}
            {result.technicalDetails && (
              <details open={detailsOpen} onToggle={(event) => setDetailsOpen(event.currentTarget.open)}>
                <summary>查看技術詳細資料</summary>
                <pre className="preview">{JSON.stringify(result.technicalDetails, null, 2)}</pre>
              </details>
            )}
          </>
        ) : (
          <p className="muted">任務結果會在這裡顯示。</p>
        )}
      </section>
    </div>
  );
}

function TasksPage(): React.ReactElement {
  return <section className="panel"><h2>任務紀錄</h2><p>任務、計畫與觀察紀錄會保存在本機資料庫。</p></section>;
}

function AutomationsPage(): React.ReactElement {
  return <section className="panel"><h2>自動化</h2><p>排程資料模型已存在，背景自動執行仍保留給後續階段。</p></section>;
}

function SettingsPage({ status, bridgeReady }: { status: RuntimeStatus | null; bridgeReady: boolean }): React.ReactElement {
  const [provider, setProvider] = useState<ProviderSettings | null>(null);
  const [keyInput, setKeyInput] = useState("");
  const [model, setModel] = useState("");
  const [message, setMessage] = useState<string | null>(null);
  const [developerOpen, setDeveloperOpen] = useState(false);

  const load = async () => {
    const bridge = getDesktopBridge();
    if (!bridge) {
      return;
    }
    const settings = await bridge.getProviderSettings();
    setProvider(settings);
    setModel(settings.model);
  };

  useEffect(() => {
    void load();
  }, []);

  const updateSettings = async (payload: Partial<ProviderSettings>) => {
    const bridge = getDesktopBridge();
    if (!bridge) {
      return;
    }
    const next = await bridge.updateProviderSettings(payload);
    setProvider(next);
    setModel(next.model);
    setMessage("設定已更新。");
  };

  const saveKey = async () => {
    const bridge = getDesktopBridge();
    if (!bridge) {
      return;
    }
    const next = await bridge.saveProviderKey(keyInput);
    setProvider(next);
    setKeyInput("");
    setMessage("API Key 已安全儲存。");
  };

  const deleteKey = async () => {
    const bridge = getDesktopBridge();
    if (!bridge) {
      return;
    }
    const next = await bridge.deleteProviderKey();
    setProvider(next);
    setMessage("API Key 已刪除。");
  };

  return (
    <div className="settings-layout">
      <section className="panel">
        <h2>Provider 設定</h2>
        <div className="segmented">
          <button className={provider?.mode !== "openai" ? "active" : ""} onClick={() => updateSettings({ mode: "local" })}>本機指令模式</button>
          <button className={provider?.mode === "openai" ? "active" : ""} onClick={() => updateSettings({ mode: "openai" })}>OpenAI 模式</button>
        </div>
        <label htmlFor="model">模型 ID</label>
        <div className="inline-form">
          <input id="model" value={model} onChange={(event) => setModel(event.target.value)} />
          <button onClick={() => updateSettings({ model })}>儲存</button>
        </div>
        <p>API Key：{provider?.apiKeyConfigured ? "已設定" : "未設定"}</p>
        <div className="inline-form">
          <input type="password" value={keyInput} onChange={(event) => setKeyInput(event.target.value)} placeholder="貼上新的 OpenAI API Key" />
          <button disabled={!keyInput.trim()} onClick={saveKey}>儲存 Key</button>
          <button onClick={deleteKey}><Trash2 size={16} />刪除</button>
        </div>
        {message && <div className="notice">{message}</div>}
      </section>

      <section className="panel">
        <h2>系統診斷</h2>
        <dl>
          <dt>桌面橋接</dt>
          <dd>{bridgeReady ? "已連線" : "未連線"}</dd>
          <dt>執行核心</dt>
          <dd>{status?.state === "running" ? "正常" : "啟動中"}</dd>
          <dt>資料庫</dt>
          <dd>{status?.databaseReady ? "ready" : "pending"}</dd>
          <dt>Token 狀態</dt>
          <dd>{String(status?.tokenExposedToRenderer ?? false)}</dd>
        </dl>
      </section>

      <details className="panel wide" open={developerOpen} onToggle={(event) => setDeveloperOpen(event.currentTarget.open)}>
        <summary>進階設定 · 開發者工具</summary>
        <p className="muted">開發與診斷用途。一般任務請回到助理首頁用中文描述。</p>
        <DeveloperTools />
      </details>
    </div>
  );
}

function DeveloperTools(): React.ReactElement {
  const [taskType, setTaskType] = useState("LIST_DIRECTORY");
  const [path, setPath] = useState(".");
  const [destination, setDestination] = useState("");
  const [content, setContent] = useState("");
  const [workspace, setWorkspace] = useState<Workspace | null>(null);
  const [registeredApps, setRegisteredApps] = useState<RegisteredApp[]>([]);
  const [result, setResult] = useState<TaskResult | null>(null);

  useEffect(() => {
    const bridge = getDesktopBridge();
    if (!bridge) {
      return;
    }
    void Promise.all([bridge.getWorkspaces(), bridge.getRegisteredApps()]).then(([workspaces, apps]) => {
      setWorkspace(workspaces[0] ?? null);
      setRegisteredApps(apps.apps ?? []);
    });
  }, []);

  const runTask = async () => {
    const bridge = getDesktopBridge();
    if (!bridge) {
      return;
    }
    setResult(await bridge.createStructuredTask({ task_type: taskType, workspace_id: workspace?.id, path, destination: destination || undefined, content: content || undefined, query: content || undefined, search_content: taskType === "SEARCH_FILES" }));
  };

  return (
    <div className="form-grid">
      <select value={taskType} onChange={(event) => setTaskType(event.target.value)}>
        {["LIST_DIRECTORY", "STAT_PATH", "READ_TEXT", "SEARCH_FILES", "HASH_FILE", "FIND_DUPLICATES", "CREATE_DIRECTORY", "WRITE_NEW_TEXT", "COPY_FILE", "MOVE_FILE", "RENAME_FILE", "OVERWRITE_TEXT", "SYSTEM_INFO", "LIST_PROCESSES", "LIST_REGISTERED_APPS", "LAUNCH_REGISTERED_APP"].map((item) => (
          <option key={item} value={item}>{item}</option>
        ))}
      </select>
      <input value={path} onChange={(event) => setPath(event.target.value)} placeholder="relative/path.txt" />
      <input value={destination} onChange={(event) => setDestination(event.target.value)} placeholder="destination relative path" />
      <textarea value={content} onChange={(event) => setContent(event.target.value)} placeholder="content or search query" />
      {taskType === "LAUNCH_REGISTERED_APP" && <select>{registeredApps.map((app) => <option key={app.id}>{app.name}</option>)}</select>}
      <button onClick={runTask}>執行開發者任務</button>
      {result && <pre className="preview">{JSON.stringify(result.observation ?? {}, null, 2)}</pre>}
    </div>
  );
}

function safeError(event: unknown, fallback: string): string {
  const message = event instanceof Error ? event.message : fallback;
  return /SELECT|SQLAlchemy|sqlalche\.me|sqlite|Traceback|undo_records/i.test(message) ? fallback : message;
}

createRoot(document.getElementById("root")!).render(<App />);
