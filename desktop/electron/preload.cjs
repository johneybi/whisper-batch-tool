const { contextBridge, ipcRenderer } = require("electron");

contextBridge.exposeInMainWorld("whisperDesktop", {
  addFiles: () => ipcRenderer.invoke("dialog:addFiles"),
  addFolder: (recursive) => ipcRenderer.invoke("dialog:addFolder", recursive),
  selectOutputFolder: () => ipcRenderer.invoke("dialog:selectOutputFolder"),
  selfTest: () => ipcRenderer.invoke("app:selfTest"),
  startTranscription: (payload) => ipcRenderer.invoke("transcription:start", payload),
  cancelTranscription: () => ipcRenderer.invoke("transcription:cancel"),
  openPath: (folderPath) => ipcRenderer.invoke("shell:openPath", folderPath),
  onTranscriptionEvent: (callback) => {
    const listener = (_event, message) => callback(message);
    ipcRenderer.on("transcription:event", listener);
    return () => ipcRenderer.removeListener("transcription:event", listener);
  }
});
