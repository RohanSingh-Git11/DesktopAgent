const path = require("node:path");
const fs = require("node:fs");
const { spawn } = require("node:child_process");
const readline = require("node:readline");
const { app, BrowserWindow, ipcMain, globalShortcut, screen } = require("electron");

const ROOT_DIR = path.resolve(__dirname, "..");
const PYTHON_CMD = "C:\\Python313\\python.exe";
let mainWindow = null;
let backendProcess = null;
let backendRestartTimer = null;
let appShuttingDown = false;
let activeJob = null;
let settingsCache = null;

const DEFAULT_SETTINGS = {
  hotkey: "Super+J",
  apiKeys: [],
  model: "gemini-2.5-flash",
  proxyUrl: "",
  allowScraperFallback: true,
  maxSteps: 8,
  requireConfirmation: true,
  autoApproveRepeats: true,
  verifyAfterEachStep: true,
  recoveryRetries: 2,
  enableOcr: false,
  enabledSkillPacks: [
    "planning-and-task-breakdown",
    "debugging-and-error-recovery",
    "frontend-ui-engineering"
  ]
};

function forwardEvent(payload) {
  if (mainWindow && !mainWindow.isDestroyed()) {
    mainWindow.webContents.send("scraper:event", payload);
  }
}

function backendCommand() {
  if (app.isPackaged) {
    const exeName = process.platform === "win32" ? "thinking-surface-backend.exe" : "thinking-surface-backend";
    return {
      command: path.join(process.resourcesPath, "backend", exeName),
      args: []
    };
  }

  return {
    command: PYTHON_CMD,
    args: ["desktop_backend.py"]
  };
}

function backendRuntimeDir() {
  if (!app.isPackaged) {
    return ROOT_DIR;
  }

  const runtimeDir = path.join(app.getPath("userData"), "runtime");
  fs.mkdirSync(runtimeDir, { recursive: true });
  return runtimeDir;
}

function settingsPath() {
  return path.join(app.getPath("userData"), "command-center-settings.json");
}

function loadSettings() {
  if (settingsCache) {
    return settingsCache;
  }
  try {
    const raw = fs.readFileSync(settingsPath(), "utf8");
    settingsCache = { ...DEFAULT_SETTINGS, ...JSON.parse(raw) };
  } catch {
    settingsCache = { ...DEFAULT_SETTINGS };
  }
  return settingsCache;
}

function saveSettings(nextSettings) {
  const clean = {
    ...DEFAULT_SETTINGS,
    ...nextSettings,
    apiKeys: Array.isArray(nextSettings?.apiKeys)
      ? nextSettings.apiKeys.map((key) => String(key).trim()).filter(Boolean)
      : []
  };
  settingsCache = clean;
  fs.mkdirSync(path.dirname(settingsPath()), { recursive: true });
  fs.writeFileSync(settingsPath(), JSON.stringify(clean, null, 2));
  sendBackendCommand({ type: "agent_settings", settings: clean });
  registerHotkey(clean.hotkey);
  return clean;
}

function registerHotkey(accelerator = "Super+J") {
  globalShortcut.unregisterAll();
  const ok = globalShortcut.register(accelerator, () => {
    toggleCommandCenter();
  });
  if (!ok) {
    forwardEvent({
      type: "warning",
      message: `Could not register ${accelerator}. Try another shortcut in Settings.`
    });
  }
}

function positionCommandCenter() {
  if (!mainWindow || mainWindow.isDestroyed()) {
    return;
  }
  const display = screen.getDisplayNearestPoint(screen.getCursorScreenPoint());
  const width = 980;
  const height = 680;
  const x = Math.round(display.workArea.x + (display.workArea.width - width) / 2);
  const y = Math.round(display.workArea.y + Math.max(32, display.workArea.height * 0.12));
  mainWindow.setBounds({ x, y, width, height }, false);
}

function showCommandCenter() {
  if (!mainWindow || mainWindow.isDestroyed()) {
    createWindow();
  }
  positionCommandCenter();
  mainWindow.show();
  mainWindow.focus();
  mainWindow.webContents.send("command-center:focus");
}

function toggleCommandCenter() {
  if (!mainWindow || mainWindow.isDestroyed()) {
    createWindow();
    return;
  }
  if (mainWindow.isVisible() && mainWindow.isFocused()) {
    mainWindow.hide();
    return;
  }
  showCommandCenter();
}

function startBackend() {
  if (backendProcess) {
    return;
  }

  const { command, args } = backendCommand();
  const cwd = backendRuntimeDir();

  if (app.isPackaged && !fs.existsSync(command)) {
    forwardEvent({
      type: "error",
      message: `Packaged backend not found at ${command}`
    });
    forwardEvent({ type: "backend_state", state: "degraded" });
    return;
  }

  const child = spawn(command, args, {
    cwd,
    stdio: ["pipe", "pipe", "pipe"],
    windowsHide: true
  });

  backendProcess = child;
  forwardEvent({ type: "backend_booting", command, cwd });
  sendBackendCommand({ type: "agent_settings", settings: loadSettings() });

  const stdout = readline.createInterface({ input: child.stdout });
  stdout.on("line", (line) => {
    if (!line.trim()) {
      return;
    }

    try {
      const payload = JSON.parse(line);
      if (payload.type === "result" || payload.type === "pdf_scan_result" || payload.type === "agent_task_finished" || payload.type === "stopped") {
        activeJob = null;
      }
      if (payload.type === "error" && payload.request_id && activeJob?.requestId === payload.request_id) {
        activeJob = null;
      }
      forwardEvent(payload);
    } catch (error) {
      forwardEvent({ type: "bridge_error", message: line });
    }
  });

  const stderr = readline.createInterface({ input: child.stderr });
  stderr.on("line", (line) => {
    forwardEvent({ type: "backend_log", message: line });
  });

  child.on("error", (error) => {
    forwardEvent({ type: "error", message: error.message });
    forwardEvent({ type: "backend_state", state: "degraded", message: error.message });
  });

  child.on("close", (code) => {
    backendProcess = null;
    activeJob = null;
    forwardEvent({ type: "process_exit", code, stopped: appShuttingDown });

    if (!appShuttingDown) {
      forwardEvent({ type: "backend_state", state: "restarting" });
      backendRestartTimer = setTimeout(() => {
        backendRestartTimer = null;
        startBackend();
      }, 900);
    }
  });
}

function sendBackendCommand(payload) {
  if (!backendProcess || !backendProcess.stdin || backendProcess.killed) {
    return false;
  }

  backendProcess.stdin.write(`${JSON.stringify(payload)}\n`);
  return true;
}

function createWindow() {
  mainWindow = new BrowserWindow({
    width: 980,
    height: 680,
    minWidth: 840,
    minHeight: 580,
    frame: false,
    show: false,
    resizable: true,
    movable: true,
    alwaysOnTop: true,
    skipTaskbar: true,
    backgroundColor: "#f8f4ec",
    title: "Desktop Command Center",
    titleBarStyle: "hidden",
    trafficLightPosition: { x: 18, y: 18 },
    webPreferences: {
      preload: path.join(__dirname, "preload.js"),
      contextIsolation: true,
      nodeIntegration: false
    }
  });

  mainWindow.loadFile(path.join(__dirname, "renderer", "index.html"));
  mainWindow.once("ready-to-show", () => {
    positionCommandCenter();
    mainWindow.show();
  });

  mainWindow.on("blur", () => {
    if (!activeJob) {
      mainWindow?.webContents.send("command-center:blur");
    }
  });
}

function clearActiveJob() {
  activeJob = null;
}

function stopActiveJob(reason = "stopped") {
  if (!activeJob) {
    return;
  }

  sendBackendCommand({ type: "stop", reason, request_id: activeJob.requestId });
}

function submitPrompt(prompt) {
  if (activeJob) {
    return { ok: false, error: "A generation is already running." };
  }

  const requestId = `req-${Date.now()}`;
  activeJob = { requestId, prompt };

  if (!sendBackendCommand({ type: "submit", prompt, request_id: requestId })) {
    clearActiveJob();
    return { ok: false, error: "Backend is not ready yet." };
  }

  return { ok: true, requestId };
}

function submitAgentTask(prompt) {
  if (activeJob) {
    return { ok: false, error: "A task is already running." };
  }

  const requestId = `agent-${Date.now()}`;
  activeJob = { requestId, prompt };

  if (!sendBackendCommand({ type: "agent_task", prompt, request_id: requestId })) {
    clearActiveJob();
    return { ok: false, error: "Backend is not ready yet." };
  }

  return { ok: true, requestId };
}

function scanPdf(pdfPath) {
  if (activeJob) {
    return { ok: false, error: "A generation or PDF scan is already running." };
  }

  const resolvedPath = path.resolve(String(pdfPath || ""));
  if (!resolvedPath.toLowerCase().endsWith(".pdf")) {
    return { ok: false, error: "Drop a PDF file." };
  }
  if (!fs.existsSync(resolvedPath)) {
    return { ok: false, error: "PDF file was not found." };
  }

  const requestId = `pdf-${Date.now()}`;
  activeJob = { requestId, pdfPath: resolvedPath };

  if (!sendBackendCommand({ type: "scan_pdf", path: resolvedPath, request_id: requestId })) {
    clearActiveJob();
    return { ok: false, error: "Backend is not ready yet." };
  }

  return { ok: true, requestId };
}

function shutdownBackend() {
  appShuttingDown = true;

  if (backendRestartTimer) {
    clearTimeout(backendRestartTimer);
    backendRestartTimer = null;
  }

  if (!backendProcess) {
    return;
  }

  sendBackendCommand({ type: "shutdown" });
  setTimeout(() => {
    if (backendProcess && !backendProcess.killed) {
      backendProcess.kill();
    }
  }, 1000);
}

app.whenReady().then(() => {
  loadSettings();
  createWindow();
  startBackend();
  registerHotkey(loadSettings().hotkey);

  ipcMain.handle("window:minimize", () => {
    BrowserWindow.getFocusedWindow()?.hide();
  });

  ipcMain.handle("window:close", () => {
    stopActiveJob("window_close");
    BrowserWindow.getFocusedWindow()?.close();
  });

  ipcMain.handle("scraper:submit", (_event, prompt) => {
    return submitPrompt(prompt);
  });

  ipcMain.handle("agent:run", (_event, prompt) => {
    return submitAgentTask(prompt);
  });

  ipcMain.handle("settings:get", () => {
    return loadSettings();
  });

  ipcMain.handle("settings:save", (_event, settings) => {
    return saveSettings(settings || {});
  });

  ipcMain.handle("scraper:stop", () => {
    stopActiveJob("user_stop");
    return { ok: true };
  });

  ipcMain.handle("agent:stop", () => {
    stopActiveJob("panic_stop");
    return { ok: true };
  });

  ipcMain.handle("agent:approval", (_event, payload) => {
    const approvalId = String(payload?.approvalId || "");
    const decision = String(payload?.decision || "deny");
    sendBackendCommand({ type: "agent_approval_response", approval_id: approvalId, decision });
    return { ok: true };
  });

  ipcMain.handle("pdf:scan", (_event, pdfPath) => {
    return scanPdf(pdfPath);
  });

  app.on("activate", () => {
    if (BrowserWindow.getAllWindows().length === 0) {
      createWindow();
    }
    if (!backendProcess) {
      startBackend();
    }
  });
});

app.on("will-quit", () => {
  globalShortcut.unregisterAll();
});

app.on("window-all-closed", () => {
  stopActiveJob("window_all_closed");
  shutdownBackend();
  if (process.platform !== "darwin") {
    app.quit();
  }
});

app.on("before-quit", () => {
  shutdownBackend();
});
