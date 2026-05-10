const { contextBridge, ipcRenderer, webUtils } = require("electron");

contextBridge.exposeInMainWorld("desktopBridge", {
  minimizeWindow: () => ipcRenderer.invoke("window:minimize"),
  closeWindow: () => ipcRenderer.invoke("window:close"),
  runAgentTask: (prompt) => ipcRenderer.invoke("agent:run", prompt),
  stopAgentTask: () => ipcRenderer.invoke("agent:stop"),
  resolveApproval: (approvalId, decision) => ipcRenderer.invoke("agent:approval", { approvalId, decision }),
  getSettings: () => ipcRenderer.invoke("settings:get"),
  saveSettings: (settings) => ipcRenderer.invoke("settings:save", settings),
  submitPrompt: (prompt) => ipcRenderer.invoke("scraper:submit", prompt),
  stopPrompt: () => ipcRenderer.invoke("scraper:stop"),
  scanPdf: (pdfPath) => ipcRenderer.invoke("pdf:scan", pdfPath),
  getFilePath: (file) => webUtils.getPathForFile(file),
  onEvent: (callback) => {
    const listener = (_event, payload) => callback(payload);
    ipcRenderer.on("scraper:event", listener);
    return () => ipcRenderer.removeListener("scraper:event", listener);
  },
  onFocusRequest: (callback) => {
    const listener = () => callback();
    ipcRenderer.on("command-center:focus", listener);
    return () => ipcRenderer.removeListener("command-center:focus", listener);
  },
  onBlurRequest: (callback) => {
    const listener = () => callback();
    ipcRenderer.on("command-center:blur", listener);
    return () => ipcRenderer.removeListener("command-center:blur", listener);
  }
});
