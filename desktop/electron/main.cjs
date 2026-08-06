const { app, BrowserWindow, dialog, ipcMain, shell } = require("electron");
const path = require("node:path");
const { spawn } = require("node:child_process");
const fs = require("node:fs");
const {
  createOutputAccessStore,
  mediaExtensions,
  validatePathArray,
  validateTranscriptionPayload
} = require("./ipcSecurity.cjs");
const { discoverMediaPaths } = require("./mediaDiscovery.cjs");
const { selectPythonExecutable } = require("./runtimeSelection.cjs");

const rootDir = path.resolve(__dirname, "..", "..");
const desktopDir = path.resolve(__dirname, "..");
let mainWindow = null;
let activeWorker = null;
let activeMediaScan = null;
const outputAccess = createOutputAccessStore();

function pythonExecutable() {
  return selectPythonExecutable(rootDir, fs.existsSync);
}

function workerPath() {
  return path.join(desktopDir, "python", "worker.py");
}

function workerEnv() {
  return {
    ...process.env,
    PYTHONUTF8: "1",
    PYTHONIOENCODING: "utf-8"
  };
}

function isMediaPath(filePath) {
  return mediaExtensions.has(path.extname(String(filePath)).replace(".", "").toLowerCase());
}

async function resolveMediaPaths(inputPaths, recursive = true) {
  if (activeMediaScan) {
    activeMediaScan.abort();
  }
  const controller = new AbortController();
  activeMediaScan = controller;
  try {
    return await discoverMediaPaths(inputPaths, {
      fsModule: fs,
      isMediaFile: isMediaPath,
      recursive,
      signal: controller.signal
    });
  } finally {
    if (activeMediaScan === controller) {
      activeMediaScan = null;
    }
  }
}

const mediaDialogExtensions = Array.from(mediaExtensions).sort();


function createWindow() {
  const smokeReportPath = process.env.WHISPER_DESKTOP_SMOKE_REPORT || "";
  const smokeScreenshotPath = process.env.WHISPER_DESKTOP_SMOKE_SCREENSHOT || "";

  mainWindow = new BrowserWindow({
    width: 1560,
    height: 1120,
    minWidth: 1360,
    minHeight: 900,
    show: !smokeReportPath,
    titleBarStyle: "hidden",
    titleBarOverlay: process.platform === "win32" ? {
      color: "#ffffff",
      symbolColor: "#101828",
      height: 48
    } : true,
    title: "Whisper Batch Transcriber",
    backgroundColor: "#f8fafc",
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

  if (smokeReportPath) {
    mainWindow.webContents.once("did-finish-load", async () => {
      try {
        const smokeWaitMs = Number(process.env.WHISPER_DESKTOP_SMOKE_WAIT_MS || 2500);
        await new Promise((resolve) => setTimeout(resolve, smokeWaitMs));
        const report = await mainWindow.webContents.executeJavaScript(`
          (() => {
            const bodyText = document.body.innerText || "";
            const buttons = Array.from(document.querySelectorAll("button"))
              .map((button) => button.innerText.trim())
              .filter(Boolean);
            return {
              title: document.querySelector("h1")?.innerText || "",
              width: window.innerWidth,
              height: window.innerHeight,
              hasDropzone: bodyText.includes("Drop audio or video files here"),
              hasSetup: bodyText.includes("Transcription Setup"),
              hasTranslateToEnglish: bodyText.includes("Translate to English"),
              hasResultPreview: bodyText.includes("Result Preview"),
              hasFfmpegReady: bodyText.includes("ffmpeg ready"),
              buttons
            };
          })()
        `);

        if (smokeScreenshotPath) {
          const image = await mainWindow.capturePage();
          await fs.promises.mkdir(path.dirname(smokeScreenshotPath), { recursive: true });
          await fs.promises.writeFile(smokeScreenshotPath, image.toPNG());
          report.screenshotBytes = image.toPNG().length;
        }

        await fs.promises.mkdir(path.dirname(smokeReportPath), { recursive: true });
        await fs.promises.writeFile(smokeReportPath, JSON.stringify(report, null, 2), "utf8");
        app.quit();
      } catch (error) {
        await fs.promises.mkdir(path.dirname(smokeReportPath), { recursive: true });
        await fs.promises.writeFile(smokeReportPath, JSON.stringify({ error: error.message }, null, 2), "utf8");
        app.exit(1);
      }
    });
  }
}

function runWorker(command, payload = {}, onEvent) {
  return new Promise((resolve, reject) => {
    const child = spawn(pythonExecutable(), [workerPath(), command], {
      cwd: rootDir,
      env: workerEnv(),
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
      { name: "Audio and video files", extensions: mediaDialogExtensions },
      { name: "All files", extensions: ["*"] }
    ]
  });
  if (result.canceled) return [];
  return (await resolveMediaPaths(result.filePaths, false)).files;
});

ipcMain.handle("dialog:addFolder", async (_event, recursive) => {
  const result = await dialog.showOpenDialog(mainWindow, {
    properties: ["openDirectory"]
  });
  if (result.canceled || !result.filePaths[0]) return [];
  return (await resolveMediaPaths([result.filePaths[0]], Boolean(recursive))).files;
});

ipcMain.handle("files:resolveDroppedPaths", async (_event, paths, recursive) => {
  const inputPaths = validatePathArray(paths, "paths", { allowEmpty: true });
  return resolveMediaPaths(inputPaths, Boolean(recursive));
});

ipcMain.handle("files:cancelResolve", async () => {
  activeMediaScan?.abort();
  return true;
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

ipcMain.handle("app:runtimeInfo", async () => {
  return runWorker("runtime-info");
});

ipcMain.handle("window:minimize", () => {
  mainWindow?.minimize();
});

ipcMain.handle("window:toggleMaximize", () => {
  if (!mainWindow) return false;
  if (mainWindow.isMaximized()) {
    mainWindow.unmaximize();
    return false;
  }
  mainWindow.maximize();
  return true;
});

ipcMain.handle("window:close", () => {
  mainWindow?.close();
});

ipcMain.handle("shell:openPath", async (_event, targetPath) => {
  if (!targetPath) return;
  const allowedPath = outputAccess.assertShellOutputTarget(targetPath);
  await shell.openPath(allowedPath);
});

ipcMain.handle("shell:showItemInFolder", async (_event, filePath) => {
  if (!filePath) return;
  const allowedPath = outputAccess.assertShellOutputTarget(filePath, { requireFile: true });
  shell.showItemInFolder(allowedPath);
});

ipcMain.handle("fs:readTextFile", async (_event, filePath) => {
  if (!filePath) return "";
  const resolved = outputAccess.assertReadableOutputFile(filePath);
  return fs.promises.readFile(resolved, "utf8");
});

ipcMain.handle("transcription:start", async (_event, payload) => {
  if (activeWorker) {
    throw new Error("A transcription job is already running.");
  }
  const safePayload = validateTranscriptionPayload(payload);
  outputAccess.reset();

  return new Promise((resolve, reject) => {
    const child = spawn(pythonExecutable(), [workerPath(), "transcribe"], {
      cwd: rootDir,
      env: workerEnv(),
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
            outputAccess.addOutputFiles(finalPayload?.output_files);
          } else if (message.type === "file-state" && message.payload?.state === "done") {
            outputAccess.addOutputFiles(message.payload.outputFiles);
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

    child.stdin.write(JSON.stringify(safePayload));
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
