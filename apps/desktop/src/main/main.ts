import { app, BrowserWindow, Menu, Tray, nativeImage } from "electron";
import { appendFileSync, mkdirSync } from "node:fs";
import { join } from "node:path";
import { createDefaultRuntimeManager } from "./runtimeManager.js";
import { registerIpc } from "./ipc.js";

app.setName("CLM Assistant Desktop");

const singleInstanceLock = app.requestSingleInstanceLock();
if (!singleInstanceLock) {
  app.quit();
}

let mainWindow: BrowserWindow | null = null;
let tray: Tray | null = null;
let isQuitting = false;
const runtime = createDefaultRuntimeManager();

function smokeLog(message: string): void {
  if (process.env.CLM_ELECTRON_SMOKE_LOG) {
    mkdirSync(join(process.env.CLM_PROJECT_ROOT ?? process.cwd(), ".runtime"), { recursive: true });
    appendFileSync(process.env.CLM_ELECTRON_SMOKE_LOG, `${new Date().toISOString()} ${message}\n`, "utf8");
  }
}

async function createWindow(): Promise<void> {
  mainWindow = new BrowserWindow({
    width: 1180,
    height: 760,
    minWidth: 980,
    minHeight: 640,
    title: "CLM Assistant Desktop",
    webPreferences: {
      preload: join(app.getAppPath(), "dist", "preload", "preload.js"),
      nodeIntegration: false,
      contextIsolation: true,
      sandbox: true
    }
  });

  const devUrl = process.env.VITE_DEV_SERVER_URL ?? "http://127.0.0.1:5173";
  if (!app.isPackaged) {
    await mainWindow.loadURL(devUrl);
  } else {
    await mainWindow.loadFile(join(app.getAppPath(), "dist", "renderer", "index.html"));
  }

  mainWindow.on("close", (event) => {
    if (!isQuitting) {
      event.preventDefault();
      mainWindow?.hide();
    }
  });
}

function createTray(): void {
  const icon = nativeImage.createEmpty();
  tray = new Tray(icon);
  tray.setToolTip("CLM Assistant Desktop");
  tray.setContextMenu(
    Menu.buildFromTemplate([
      { label: "Open", click: () => mainWindow?.show() },
      {
        label: "Quit",
        click: async () => {
          isQuitting = true;
          await runtime.stop();
          app.quit();
        }
      }
    ])
  );
}

app.whenReady()
  .then(async () => {
    smokeLog("electron-ready");
    const watchdog = process.env.CLM_ELECTRON_SMOKE === "1"
      ? setTimeout(() => {
          smokeLog("watchdog-timeout");
          app.exit(2);
        }, 20000)
      : null;
    registerIpc(runtime);
    await runtime.start();
    smokeLog("runtime-started");
    if (process.env.CLM_ELECTRON_SMOKE === "1") {
      await runtime.stop();
      smokeLog("runtime-stopped");
      if (watchdog) {
        clearTimeout(watchdog);
      }
      app.exit(0);
      return;
    }
    createTray();
    await createWindow();
  })
  .catch(async (error: unknown) => {
    smokeLog(`startup-error ${error instanceof Error ? error.message : String(error)}`);
    console.error(error);
    await runtime.stop();
    app.exit(1);
  });

app.on("second-instance", () => {
  mainWindow?.show();
  mainWindow?.focus();
});

app.on("before-quit", async () => {
  isQuitting = true;
  await runtime.stop();
});
