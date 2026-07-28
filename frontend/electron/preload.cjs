const { contextBridge, ipcRenderer } = require("electron");

contextBridge.exposeInMainWorld("personalFinance", {
  platform: process.platform,
  apiBase: process.env.PERSONAL_FINANCE_API || "http://127.0.0.1:8000",
  isDesktop: true,
  openExternal: (url) => ipcRenderer.invoke("open-external", url),
  onBackupBeforeQuit: (handler) => {
    const listener = () => {
      Promise.resolve(handler())
        .catch(() => undefined)
        .finally(() => ipcRenderer.send("backup-before-quit-done"));
    };
    ipcRenderer.on("backup-before-quit", listener);
    return () => ipcRenderer.removeListener("backup-before-quit", listener);
  },
});
