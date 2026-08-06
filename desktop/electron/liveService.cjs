const fs = require("node:fs");
const path = require("node:path");
const { spawn } = require("node:child_process");

const DEFAULT_LIVE_PORT = 8765;
const ACTIVE_RUN_STATES = new Set([
  "queued", "probing", "capturing", "transcribing", "draining", "reconnecting", "stopping"
]);

function resolveLiveProjectRoot(env = process.env, platform = process.platform) {
  const configured = String(env.AUTO_NEWS_SCRIPTER_ROOT || "").trim();
  if (configured) return path.resolve(configured);
  return platform === "win32" ? "E:\\auto-news-scripter" : "";
}

function validateLiveRunPayload(value) {
  if (!value || typeof value !== "object" || Array.isArray(value)) {
    throw new Error("Live transcription payload must be an object.");
  }
  const sourceUrl = String(value.source_url || "").trim();
  let parsed;
  try {
    parsed = new URL(sourceUrl);
  } catch {
    throw new Error("A valid YouTube URL is required.");
  }
  const hostname = parsed.hostname.toLowerCase().replace(/^www\./, "");
  if (!["youtube.com", "m.youtube.com", "youtu.be"].includes(hostname)) {
    throw new Error("Only YouTube URLs are supported for live transcription.");
  }
  const chunkSeconds = Number(value.chunk_seconds ?? 30);
  if (!Number.isInteger(chunkSeconds) || chunkSeconds < 10 || chunkSeconds > 600) {
    throw new Error("Chunk length must be an integer between 10 and 600 seconds.");
  }
  const title = String(value.title || "").trim();
  if (title.length > 200) throw new Error("Live transcription title is too long.");
  return {
    source_url: sourceUrl,
    title: title || null,
    chunk_seconds: chunkSeconds,
    start_from_beginning: Boolean(value.start_from_beginning)
  };
}

function createLiveServiceManager({
  env = process.env,
  platform = process.platform,
  existsSync = fs.existsSync,
  spawnImpl = spawn,
  fetchImpl = global.fetch,
  port = Number(process.env.WHISPER_LIVE_PORT || DEFAULT_LIVE_PORT),
  onLog = () => undefined
} = {}) {
  const projectRoot = resolveLiveProjectRoot(env, platform);
  const baseUrl = `http://127.0.0.1:${port}`;
  let child = null;
  let ownsService = false;

  function projectPaths() {
    return {
      python: projectRoot ? path.join(projectRoot, ".venv", "Scripts", "python.exe") : "",
      appRoot: projectRoot ? path.join(projectRoot, "services", "app") : "",
      data: projectRoot ? path.join(projectRoot, "data") : "",
      knowledge: projectRoot ? path.join(projectRoot, "data", "knowledge") : "",
      models: projectRoot ? path.join(projectRoot, "data", "models") : ""
    };
  }

  async function request(endpoint, options = {}) {
    if (typeof fetchImpl !== "function") throw new Error("This Electron runtime does not provide fetch.");
    const controller = new AbortController();
    const timeout = setTimeout(() => controller.abort(), options.timeoutMs || 5000);
    try {
      const { timeoutMs: _timeoutMs, ...fetchOptions } = options;
      const response = await fetchImpl(`${baseUrl}${endpoint}`, {
        ...fetchOptions,
        signal: controller.signal,
        headers: {
          ...(options.body ? { "Content-Type": "application/json" } : {}),
          ...(options.headers || {})
        }
      });
      const text = await response.text();
      const payload = text ? JSON.parse(text) : null;
      if (!response.ok) throw new Error(payload?.detail || `Live service request failed (${response.status}).`);
      return payload;
    } finally {
      clearTimeout(timeout);
    }
  }

  async function isRunning() {
    try {
      await request("/api/runs", { timeoutMs: 900 });
      return true;
    } catch {
      return false;
    }
  }

  function readiness() {
    const paths = projectPaths();
    if (!projectRoot) return { ready: false, detail: "AUTO_NEWS_SCRIPTER_ROOT is not configured.", projectRoot };
    if (!existsSync(paths.python)) return { ready: false, detail: `Live runtime is missing: ${paths.python}`, projectRoot };
    if (!existsSync(paths.appRoot)) return { ready: false, detail: `Live service source is missing: ${paths.appRoot}`, projectRoot };
    return { ready: true, detail: "Live transcription runtime is ready.", projectRoot };
  }

  async function initialize() {
    if (await isRunning()) return { ready: true, running: true, attached: !ownsService, projectRoot, baseUrl };
    const state = readiness();
    if (!state.ready) return { ...state, running: false, baseUrl };
    if (child) return { ready: true, running: false, starting: true, projectRoot, baseUrl };

    const paths = projectPaths();
    const sitePackages = path.join(projectRoot, ".venv", "Lib", "site-packages");
    const cudaBins = [
      path.join(sitePackages, "nvidia", "cuda_runtime", "bin"),
      path.join(sitePackages, "nvidia", "cublas", "bin"),
      path.join(sitePackages, "nvidia", "cudnn", "bin")
    ].filter(existsSync);
    const serviceEnv = {
      ...env,
      PATH: [path.join(projectRoot, ".venv", "Scripts"), ...cudaBins, env.PATH || ""].join(path.delimiter),
      PYTHONPATH: paths.appRoot,
      DATA_DIR: paths.data,
      DATABASE_PATH: path.join(paths.data, "app.db"),
      KNOWLEDGE_DIR: paths.knowledge,
      MODEL_CACHE_DIR: paths.models,
      TRANSCRIBER_MODE: "local_whisper",
      ROLLING_CHUNK_SECONDS: "30",
      ROLLING_CAPTURE_RETRIES: "3",
      ROLLING_RETRY_SECONDS: "10",
      STREAMLINK_QUALITY: "best",
      WHISPER_MODEL: env.WHISPER_LIVE_MODEL || "large-v3-turbo",
      WHISPER_LANGUAGE: env.WHISPER_LIVE_LANGUAGE || "ko",
      WHISPER_BEAM_SIZE: "5",
      WHISPER_DEVICE: env.WHISPER_LIVE_DEVICE || "cuda",
      WHISPER_COMPUTE_TYPE: env.WHISPER_LIVE_COMPUTE_TYPE || "float16",
      HF_HUB_DISABLE_SYMLINKS_WARNING: "1",
      PYTHONUTF8: "1",
      PYTHONIOENCODING: "utf-8"
    };
    child = spawnImpl(paths.python, [
      "-m", "uvicorn", "app.live_view:app", "--host", "127.0.0.1", "--port", String(port)
    ], {
      cwd: projectRoot,
      env: serviceEnv,
      windowsHide: true,
      stdio: ["ignore", "pipe", "pipe"]
    });
    ownsService = true;
    child.stdout?.on("data", (chunk) => onLog(String(chunk).trim()));
    child.stderr?.on("data", (chunk) => onLog(String(chunk).trim()));
    child.on("exit", (code) => {
      onLog(`Live service exited${code == null ? "" : ` with code ${code}`}.`);
      child = null;
      ownsService = false;
    });
    for (let attempt = 0; attempt < 40; attempt += 1) {
      if (await isRunning()) return { ready: true, running: true, attached: false, projectRoot, baseUrl };
      await new Promise((resolve) => setTimeout(resolve, 250));
    }
    shutdown();
    throw new Error("Live transcription service did not become ready.");
  }

  async function listRuns() {
    const state = await initialize();
    if (!state.ready) throw new Error(state.detail);
    return request("/api/runs");
  }

  async function createRun(payload) {
    const safePayload = validateLiveRunPayload(payload);
    const state = await initialize();
    if (!state.ready) throw new Error(state.detail);
    return request("/api/runs", { method: "POST", body: JSON.stringify(safePayload) });
  }

  async function stopRun(runId) {
    const safeRunId = String(runId || "").trim();
    if (!/^[a-f0-9-]{8,64}$/i.test(safeRunId)) throw new Error("Invalid live run ID.");
    const state = await initialize();
    if (!state.ready) throw new Error(state.detail);
    return request(`/api/runs/${safeRunId}/stop`, { method: "POST" });
  }

  async function hasActiveRuns() {
    if (!(await isRunning())) return false;
    const runs = await request("/api/runs");
    return runs.some((run) => ACTIVE_RUN_STATES.has(run.status));
  }

  function shutdown() {
    if (child && ownsService) child.kill();
    child = null;
    ownsService = false;
  }

  return { createRun, hasActiveRuns, initialize, listRuns, readiness, shutdown, stopRun };
}

module.exports = { ACTIVE_RUN_STATES, createLiveServiceManager, resolveLiveProjectRoot, validateLiveRunPayload };
