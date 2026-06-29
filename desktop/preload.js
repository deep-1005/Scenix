const { contextBridge, ipcRenderer } = require("electron");

contextBridge.exposeInMainWorld("electronAPI", {
  runGaussianSplat: (jobId) =>
    ipcRenderer.invoke("file:run-gaussian-splat", { jobId }),
  getGaussianSplatStatus: (jobId) =>
    ipcRenderer.invoke("file:gaussian-splat-status", { jobId }),
});