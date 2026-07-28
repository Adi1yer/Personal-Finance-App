const { app, BrowserWindow, shell, ipcMain } = require("electron");
const path = require("path");

const isDev = process.env.ELECTRON_DEV === "1";
const API_URL = process.env.API_URL || "http://127.0.0.1:8000";

let mainWindow = null;
let allowQuit = false;
let backupInFlight = false;

function createWindow() {
  mainWindow = new BrowserWindow({
    width: 1320,
    height: 880,
    minWidth: 960,
    minHeight: 640,
    show: false,
    title: "Personal Finance",
    titleBarStyle: "hiddenInset",
    trafficLightPosition: { x: 16, y: 18 },
    backgroundColor: "#0f1419",
    webPreferences: {
      preload: path.join(__dirname, "preload.cjs"),
      contextIsolation: true,
      nodeIntegration: false,
      sandbox: true,
    },
  });

  mainWindow.once("ready-to-show", () => mainWindow.show());

  // Always load via local HTTP so API proxy/CORS matches dev and packaged runs.
  mainWindow.loadURL("http://127.0.0.1:5173");
  if (isDev) {
    mainWindow.webContents.openDevTools({ mode: "detach" });
  }

  mainWindow.webContents.setWindowOpenHandler(({ url }) => {
    shell.openExternal(url);
    return { action: "deny" };
  });
}

function requestQuitBackupThenExit() {
  if (!mainWindow || mainWindow.isDestroyed()) {
    allowQuit = true;
    app.quit();
    return;
  }
  backupInFlight = true;
  const timeout = setTimeout(() => {
    if (!allowQuit) {
      backupInFlight = false;
      allowQuit = true;
      app.quit();
    }
  }, 45000);

  ipcMain.once("backup-before-quit-done", () => {
    clearTimeout(timeout);
    backupInFlight = false;
    allowQuit = true;
    app.quit();
  });

  mainWindow.webContents.send("backup-before-quit");
}

app.whenReady().then(createWindow);

app.on("before-quit", (event) => {
  if (allowQuit || backupInFlight) return;
  event.preventDefault();
  requestQuitBackupThenExit();
});

app.on("window-all-closed", () => {
  if (process.platform !== "darwin") app.quit();
});

app.on("activate", () => {
  if (BrowserWindow.getAllWindows().length === 0) createWindow();
});

ipcMain.handle("open-external", async (_event, url) => {
  if (typeof url === "string" && (url.startsWith("https://") || url.startsWith("http://"))) {
    await shell.openExternal(url);
  }
});

process.env.PERSONAL_FINANCE_API = API_URL;
