const { contextBridge, ipcRenderer, webUtils } = require("electron");

contextBridge.exposeInMainWorld("whisperDesktop", {
  addFiles: () => ipcRenderer.invoke("dialog:addFiles"),
  addFolder: (recursive) => ipcRenderer.invoke("dialog:addFolder", recursive),
  resolveDroppedPaths: (paths, recursive) => ipcRenderer.invoke("files:resolveDroppedPaths", paths, recursive),
  cancelFileScan: () => ipcRenderer.invoke("files:cancelResolve"),
  selectOutputFolder: () => ipcRenderer.invoke("dialog:selectOutputFolder"),
  selfTest: () => ipcRenderer.invoke("app:selfTest"),
  runtimeInfo: () => ipcRenderer.invoke("app:runtimeInfo"),
  startTranscription: (payload) => ipcRenderer.invoke("transcription:start", payload),
  cancelTranscription: () => ipcRenderer.invoke("transcription:cancel"),
  readTextFile: (filePath) => ipcRenderer.invoke("fs:readTextFile", filePath),
  openPath: (folderPath) => ipcRenderer.invoke("shell:openPath", folderPath),
  showItemInFolder: (filePath) => ipcRenderer.invoke("shell:showItemInFolder", filePath),
  getPathForFile: (file) => webUtils.getPathForFile(file),
  minimizeWindow: () => ipcRenderer.invoke("window:minimize"),
  toggleMaximizeWindow: () => ipcRenderer.invoke("window:toggleMaximize"),
  closeWindow: () => ipcRenderer.invoke("window:close"),
  onTranscriptionEvent: (callback) => {
    const listener = (_event, message) => callback(message);
    ipcRenderer.on("transcription:event", listener);
    return () => ipcRenderer.removeListener("transcription:event", listener);
  }
});
