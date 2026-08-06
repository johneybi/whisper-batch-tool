const path = require("node:path");

const defaultScanLimits = {
  maxFiles: 5000,
  maxDepth: 20,
  timeoutMs: 30000,
  yieldEvery: 50
};

function incrementReason(reasons, reason) {
  reasons[reason] = (reasons[reason] || 0) + 1;
}

function throwIfAborted(signal) {
  if (signal?.aborted) {
    const error = new Error("File scan canceled.");
    error.code = "ERR_SCAN_CANCELED";
    throw error;
  }
}

function isTimeout(startedAt, timeoutMs) {
  return timeoutMs > 0 && Date.now() - startedAt > timeoutMs;
}

function createFileInfo(filePath, stat) {
  return {
    path: filePath,
    name: path.basename(filePath),
    format: path.extname(filePath).replace(".", "").toUpperCase() || "MEDIA",
    sizeMb: Math.round(stat.size / (1024 * 1024))
  };
}

async function maybeYield(counter, yieldEvery) {
  if (yieldEvery > 0 && counter % yieldEvery === 0) {
    await new Promise((resolve) => setImmediate(resolve));
  }
}

async function discoverMediaPaths(inputPaths, options) {
  const {
    fsModule,
    isMediaFile,
    recursive = true,
    signal,
    limits = {}
  } = options;
  const resolvedLimits = { ...defaultScanLimits, ...limits };
  const files = [];
  const seenFiles = new Set();
  const visitedDirectories = new Set();
  const skippedReasons = {};
  const startedAt = Date.now();
  let scanned = 0;
  let truncated = false;
  let timedOut = false;

  async function addFile(filePath, stat) {
    const resolved = path.resolve(filePath);
    if (seenFiles.has(resolved)) {
      incrementReason(skippedReasons, "duplicate");
      return;
    }
    if (!isMediaFile(resolved)) {
      incrementReason(skippedReasons, "unsupported");
      return;
    }
    if (files.length >= resolvedLimits.maxFiles) {
      truncated = true;
      incrementReason(skippedReasons, "maxFiles");
      return;
    }
    seenFiles.add(resolved);
    files.push(createFileInfo(resolved, stat));
  }

  async function scanDirectory(directoryPath, depth) {
    throwIfAborted(signal);
    if (isTimeout(startedAt, resolvedLimits.timeoutMs)) {
      timedOut = true;
      incrementReason(skippedReasons, "timeout");
      return;
    }
    if (files.length >= resolvedLimits.maxFiles) {
      truncated = true;
      incrementReason(skippedReasons, "maxFiles");
      return;
    }
    if (depth > resolvedLimits.maxDepth) {
      incrementReason(skippedReasons, "maxDepth");
      return;
    }

    let realPath;
    try {
      realPath = await fsModule.promises.realpath(directoryPath);
    } catch {
      incrementReason(skippedReasons, "inaccessible");
      return;
    }
    if (visitedDirectories.has(realPath)) {
      incrementReason(skippedReasons, "cycle");
      return;
    }
    visitedDirectories.add(realPath);

    let entries;
    try {
      entries = await fsModule.promises.readdir(directoryPath, { withFileTypes: true });
    } catch {
      incrementReason(skippedReasons, "inaccessible");
      return;
    }

    for (const entry of entries) {
      throwIfAborted(signal);
      scanned += 1;
      await maybeYield(scanned, resolvedLimits.yieldEvery);
      if (isTimeout(startedAt, resolvedLimits.timeoutMs)) {
        timedOut = true;
        incrementReason(skippedReasons, "timeout");
        break;
      }

      const entryPath = path.join(directoryPath, entry.name);
      let stat;
      try {
        stat = await fsModule.promises.lstat(entryPath);
      } catch {
        incrementReason(skippedReasons, "inaccessible");
        continue;
      }

      if (stat.isSymbolicLink()) {
        incrementReason(skippedReasons, "symlink");
        continue;
      }
      if (stat.isFile()) {
        await addFile(entryPath, stat);
      } else if (recursive && stat.isDirectory()) {
        await scanDirectory(entryPath, depth + 1);
      } else if (stat.isDirectory()) {
        incrementReason(skippedReasons, "directory");
      } else {
        incrementReason(skippedReasons, "unsupported");
      }

      if (files.length >= resolvedLimits.maxFiles) {
        truncated = true;
        incrementReason(skippedReasons, "maxFiles");
        break;
      }
      if (timedOut) {
        break;
      }
    }
  }

  try {
    for (const inputPath of inputPaths) {
      throwIfAborted(signal);
      const resolved = path.resolve(inputPath);
      let stat;
      try {
        stat = await fsModule.promises.lstat(resolved);
      } catch {
        incrementReason(skippedReasons, "inaccessible");
        continue;
      }
      if (stat.isSymbolicLink()) {
        incrementReason(skippedReasons, "symlink");
      } else if (stat.isDirectory()) {
        await scanDirectory(resolved, 0);
      } else if (stat.isFile()) {
        await addFile(resolved, stat);
      } else {
        incrementReason(skippedReasons, "unsupported");
      }
      if (files.length >= resolvedLimits.maxFiles) {
        truncated = true;
        incrementReason(skippedReasons, "maxFiles");
        break;
      }
      if (timedOut) {
        break;
      }
    }
  } catch (error) {
    if (error.code === "ERR_SCAN_CANCELED") {
      incrementReason(skippedReasons, "canceled");
      return {
        files,
        skipped: Object.values(skippedReasons).reduce((sum, value) => sum + value, 0),
        skippedReasons,
        truncated,
        timedOut,
        canceled: true
      };
    }
    throw error;
  }

  files.sort((left, right) => left.path.localeCompare(right.path));
  return {
    files,
    skipped: Object.values(skippedReasons).reduce((sum, value) => sum + value, 0),
    skippedReasons,
    truncated,
    timedOut,
    canceled: false
  };
}

module.exports = {
  defaultScanLimits,
  discoverMediaPaths
};
