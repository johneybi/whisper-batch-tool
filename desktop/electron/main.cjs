const { app, BrowserWindow, dialog, ipcMain, shell } = require("electron");
const path = require("node:path");
const { spawn } = require("node:child_process");
const fs = require("node:fs");

const rootDir = path.resolve(__dirname, "..", "..");
const desktopDir = path.resolve(__dirname, "..");
let mainWindow = null;
let activeWorker = null;

function pythonExecutable() {
  if (process.env.WHISPER_PYTHON) {
    return process.env.WHISPER_PYTHON;
  }

  const localPython = process.platform === "win32"
    ? path.join(rootDir, ".release-venv", "Scripts", "python.exe")
    : path.join(rootDir, ".release-venv", "bin", "python");

  if (fs.existsSync(localPython)) {
    return localPython;
  }

  return process.platform === "win32" ? "python" : "python3";
}

function workerPath() {
  return path.join(desktopDir, "python", "worker.py");
}

function fileInfo(filePath) {
  const stat = fs.statSync(filePath);
  return {
    path: filePath,
    name: path.basename(filePath),
    format: path.extname(filePath).replace(".", "").toUpperCase() || "MEDIA",
    sizeMb: Math.round(stat.size / (1024 * 1024))
  };
}

function createWindow() {
  mainWindow = new BrowserWindow({
    width: 1440,
    height: 920,
    minWidth: 1120,
    minHeight: 760,
    title: "Whisper Batch Transcriber",
    backgroundColor: "#f7f9fc",
    webPreferences: {
      preload: path.join(__dirname, "preload.cjs"),
      contextIsolation: true,
      nodeIntegration: false
    }
  });

  const devUrl = process.env.VITE_DEV_SERVER_URL;
  if (devUrl) {
    mainWindow.loadURL(devUrl);
  } else {
    mainWindow.loadFile(path.join(desktopDir, "dist", "index.html"));
  }
}

function runWorker(command, payload = {}, onEvent) {
  return new Promise((resolve, reject) => {
    const child = spawn(pythonExecutable(), [workerPath(), command], {
      cwd: rootDir,
      stdio: ["pipe", "pipe", "pipe"]
    });

    let stdoutBuffer = "";
    let stderr = "";
    let finalPayload = null;

    child.stdout.on("data", (chunk) => {
      stdoutBuffer += chunk.toString();
      const lines = stdoutBuffer.split(/\r?\n/);
      stdoutBuffer = lines.pop() ?? "";

      for (const line of lines) {
        if (!line.trim()) continue;
        try {
          const message = JSON.parse(line);
          if (message.type === "done") {
            finalPayload = message.payload ?? null;
          }
          onEvent?.(message);
        } catch (error) {
          onEvent?.({ type: "log", payload: `Unparsed worker output: ${line}` });
        }
      }
    });

    child.stderr.on("data", (chunk) => {
      stderr += chunk.toString();
    });

    child.on("error", reject);
    child.on("close", (code) => {
      if (code === 0) {
        resolve(finalPayload);
      } else {
        reject(new Error(stderr.trim() || `Worker exited with code ${code}`));
      }
    });

    child.stdin.write(JSON.stringify(payload));
    child.stdin.end();
  });
}

app.whenReady().then(() => {
  createWindow();

  app.on("activate", () => {
    if (BrowserWindow.getAllWindows().length === 0) createWindow();
  });
});

app.on("window-all-closed", () => {
  if (process.platform !== "darwin") app.quit();
});

ipcMain.handle("dialog:addFiles", async () => {
  const result = await dialog.showOpenDialog(mainWindow, {
    properties: ["openFile", "multiSelections"],
    filters: [
      { name: "Audio and video files", extensions: ["mp3", "wav", "m4a", "flac", "aac", "ogg", "opus", "wma", "aiff", "alac", "amr", "mp4", "mov", "mkv", "webm", "avi", "wmv", "m4v", "flv", "mpeg", "mpg", "m2ts", "mts", "ts"] },
      { name: "All files", extensions: ["*"] }
    ]
  });
  return result.canceled ? [] : result.filePaths.map(fileInfo);
});

ipcMain.handle("dialog:addFolder", async (_event, recursive) => {
  const result = await dialog.showOpenDialog(mainWindow, {
    properties: ["openDirectory"]
  });
  if (result.canceled || !result.filePaths[0]) return [];
  return runWorker("discover", { folder: result.filePaths[0], recursive: Boolean(recursive) });
});

ipcMain.handle("dialog:selectOutputFolder", async () => {
  const result = await dialog.showOpenDialog(mainWindow, {
    properties: ["openDirectory", "createDirectory"]
  });
  return result.canceled ? "" : result.filePaths[0];
});

ipcMain.handle("app:selfTest", async () => {
  return runWorker("self-test");
});

ipcMain.handle("shell:openPath", async (_event, folderPath) => {
  if (!folderPath) return;
  await shell.openPath(folderPath);
});

ipcMain.handle("transcription:start", async (_event, payload) => {
  if (activeWorker) {
    throw new Error("A transcription job is already running.");
  }

  return new Promise((resolve, reject) => {
    const child = spawn(pythonExecutable(), [workerPath(), "transcribe"], {
      cwd: rootDir,
      stdio: ["pipe", "pipe", "pipe"]
    });
    activeWorker = child;

    let stdoutBuffer = "";
    let stderr = "";
    let finalPayload = null;

    child.stdout.on("data", (chunk) => {
      stdoutBuffer += chunk.toString();
      const lines = stdoutBuffer.split(/\r?\n/);
      stdoutBuffer = lines.pop() ?? "";
      for (const line of lines) {
        if (!line.trim()) continue;
        try {
          const message = JSON.parse(line);
          if (message.type === "done") {
            finalPayload = message.payload ?? null;
          }
          mainWindow?.webContents.send("transcription:event", message);
        } catch {
          mainWindow?.webContents.send("transcription:event", {
            type: "log",
            payload: `Unparsed worker output: ${line}`
          });
        }
      }
    });

    child.stderr.on("data", (chunk) => {
      stderr += chunk.toString();
    });

    child.on("error", (error) => {
      activeWorker = null;
      reject(error);
    });

    child.on("close", (code, signal) => {
      activeWorker = null;
      if (signal) {
        resolve({ canceled: true });
      } else if (code === 0) {
        resolve(finalPayload);
      } else {
        reject(new Error(stderr.trim() || `Worker exited with code ${code}`));
      }
    });

    child.stdin.write(JSON.stringify(payload));
    child.stdin.end();
  });
});

ipcMain.handle("transcription:cancel", async () => {
  if (activeWorker) {
    activeWorker.kill();
    activeWorker = null;
  }
  return true;
});
