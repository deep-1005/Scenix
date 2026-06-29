const { app, BrowserWindow, ipcMain } = require("electron");
const path = require("path");

function createWindow() {
  const win = new BrowserWindow({
    width: 1200, height: 860,
    title: "Forensic Digital Twin",
    webPreferences: {
      contextIsolation: true,
      preload: path.join(__dirname, "preload.js"),
    },
  });
  win.loadURL("http://localhost:5173");
}

app.whenReady().then(createWindow);
app.on("window-all-closed", () => { if (process.platform !== "darwin") app.quit(); });
app.on("activate", () => { if (BrowserWindow.getAllWindows().length === 0) createWindow(); });

// ── Gaussian Splatting IPC ─────────────────────────────────────────────────────

ipcMain.handle("file:run-gaussian-splat", async (event, { jobId }) => {
  try {
    const response = await fetch(`http://localhost:8000/jobs/${jobId}/gaussian-splat`, {
      method: "POST",
    });
    const data = await response.json();
    return { success: true, ...data };
  } catch (err) {
    return { success: false, error: err.message };
  }
});

ipcMain.handle("file:gaussian-splat-status", async (event, { jobId }) => {
  try {
    const response = await fetch(`http://localhost:8000/jobs/${jobId}/gaussian-splat/status`);
    const data = await response.json();
    return { success: true, ...data };
  } catch (err) {
    return { success: false, error: err.message };
  }
});