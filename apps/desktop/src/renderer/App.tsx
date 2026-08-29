import React, { useEffect, useState } from "react";
import { createRoot } from "react-dom/client";
import { Bot, ClipboardList, Settings, Workflow } from "lucide-react";
import type { RuntimeStatus } from "@clm/contracts";
import "./styles.css";

type Page = "assistant" | "tasks" | "automations" | "settings";

const pages: Array<{ id: Page; label: string; icon: React.ComponentType<{ size?: number }> }> = [
  { id: "assistant", label: "助理", icon: Bot },
  { id: "tasks", label: "任務", icon: ClipboardList },
  { id: "automations", label: "自動化", icon: Workflow },
  { id: "settings", label: "設定", icon: Settings }
];

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
          <strong>CLM Assistant</strong>
          <span>Foundation / Development</span>
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
            <p>Phase 1 foundation. AI task execution is not enabled yet.</p>
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
  return (
    <div className="grid">
      <section className="panel primary">
        <label htmlFor="task">自然語言任務</label>
        <textarea id="task" placeholder="描述你要在這台 Windows 主機完成的工作..." disabled />
        <div className="notice">Foundation mode: task execution, planning, approvals, and replan loop are not enabled yet.</div>
      </section>
      <section className="panel">
        <h2>Runtime</h2>
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
