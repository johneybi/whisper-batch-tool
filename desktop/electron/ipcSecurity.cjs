const path = require("node:path");

const mediaExtensions = new Set([
  "aac", "aiff", "alac", "amr", "ape", "au", "caf", "dts", "flac", "m4a", "m4b", "mid", "midi", "mp3", "oga", "ogg",
  "opus", "ra", "snd", "tta", "voc", "wav", "weba", "wma", "wv", "3g2", "3gp", "asf", "avi", "divx", "dv", "f4v",
  "flv", "m2ts", "m4v", "mkv", "mov", "mp4", "mpeg", "mpg", "mts", "mxf", "ogv", "rm", "rmvb", "ts", "vob", "webm", "wmv"
]);

const outputFormats = new Set(["txt", "srt", "vtt", "json", "tsv"]);
const modelNames = new Set(["tiny", "base", "small", "medium", "large", "large-v2", "large-v3"]);
const tasks = new Set(["transcribe", "translate"]);
const devices = new Set(["auto", "cpu", "cuda", "mps"]);
const maxPathCount = 10000;

function assertPlainObject(value, fieldName) {
  if (!value || typeof value !== "object" || Array.isArray(value)) {
    throw new Error(`${fieldName} must be an object.`);
  }
  return value;
}

function assertString(value, fieldName, { allowEmpty = false, maxLength = 4096 } = {}) {
  if (typeof value !== "string") {
    throw new Error(`${fieldName} must be a string.`);
  }
  const trimmed = value.trim();
  if (!allowEmpty && !trimmed) {
    throw new Error(`${fieldName} must not be empty.`);
  }
  if (trimmed.length > maxLength) {
    throw new Error(`${fieldName} is too long.`);
  }
  return trimmed;
}

function assertBoolean(value, fieldName) {
  if (typeof value !== "boolean") {
    throw new Error(`${fieldName} must be a boolean.`);
  }
  return value;
}

function normalizePath(value, fieldName) {
  return path.resolve(assertString(value, fieldName));
}

function validatePathArray(value, fieldName, { requireMedia = false, allowEmpty = false } = {}) {
  if (!Array.isArray(value)) {
    throw new Error(`${fieldName} must be an array.`);
  }
  if (!allowEmpty && value.length === 0) {
    throw new Error(`${fieldName} must not be empty.`);
  }
  if (value.length > maxPathCount) {
    throw new Error(`${fieldName} contains too many paths.`);
  }

  return value.map((item, index) => {
    const resolved = normalizePath(item, `${fieldName}[${index}]`);
    if (requireMedia && !isMediaFile(resolved)) {
      throw new Error(`${fieldName}[${index}] is not a supported media file.`);
    }
    return resolved;
  });
}

function isMediaFile(filePath) {
  return mediaExtensions.has(path.extname(String(filePath)).replace(".", "").toLowerCase());
}

function isOutputFile(filePath) {
  return outputFormats.has(path.extname(String(filePath)).replace(".", "").toLowerCase());
}

function validateOutputFormats(value) {
  if (!Array.isArray(value) || value.length === 0) {
    throw new Error("options.output_formats must include at least one format.");
  }
  const normalized = value.map((item, index) => assertString(item, `options.output_formats[${index}]`).toLowerCase());
  const invalid = normalized.find((item) => !outputFormats.has(item));
  if (invalid) {
    throw new Error(`Unsupported output format: ${invalid}`);
  }
  return Array.from(new Set(normalized));
}

function validateLanguage(value) {
  const language = assertString(value ?? "", "options.language", { allowEmpty: true, maxLength: 32 });
  if (!language) return "";
  if (!/^[a-zA-Z]{2,3}([_-][a-zA-Z0-9]{2,8})?$/.test(language)) {
    throw new Error("options.language must be a valid language code or empty for auto detection.");
  }
  return language;
}

function validateEnum(value, fieldName, allowed) {
  const normalized = assertString(value, fieldName);
  if (!allowed.has(normalized)) {
    throw new Error(`Unsupported ${fieldName}: ${normalized}`);
  }
  return normalized;
}

function validateTranscriptionPayload(value) {
  const payload = assertPlainObject(value, "payload");
  const options = assertPlainObject(payload.options ?? {}, "payload.options");
  const outputDir = options.output_dir == null || options.output_dir === ""
    ? null
    : normalizePath(options.output_dir, "options.output_dir");

  return {
    files: validatePathArray(payload.files, "payload.files", { requireMedia: true }),
    options: {
      model_name: validateEnum(options.model_name ?? "small", "options.model_name", modelNames),
      language: validateLanguage(options.language ?? "ko"),
      task: validateEnum(options.task ?? "transcribe", "options.task", tasks),
      device: validateEnum(options.device ?? "auto", "options.device", devices),
      output_formats: validateOutputFormats(options.output_formats ?? ["txt", "srt"]),
      output_dir: outputDir,
      condition_on_previous_text: assertBoolean(options.condition_on_previous_text ?? false, "options.condition_on_previous_text"),
      overwrite: assertBoolean(options.overwrite ?? false, "options.overwrite")
    }
  };
}

function createOutputAccessStore() {
  const outputFiles = new Set();
  const outputDirs = new Set();

  function addOutputFiles(files) {
    if (!Array.isArray(files)) return;
    for (const file of files) {
      if (typeof file !== "string" || !file.trim()) continue;
      const resolved = path.resolve(file);
      if (!isOutputFile(resolved)) continue;
      outputFiles.add(resolved);
      outputDirs.add(path.dirname(resolved));
    }
  }

  function reset() {
    outputFiles.clear();
    outputDirs.clear();
  }

  function assertReadableOutputFile(filePath) {
    const resolved = normalizePath(filePath, "filePath");
    if (!isOutputFile(resolved) || !outputFiles.has(resolved)) {
      throw new Error("File access denied. Only transcription output files from this session can be read.");
    }
    return resolved;
  }

  function assertShellOutputTarget(targetPath, { requireFile = false } = {}) {
    const resolved = normalizePath(targetPath, "targetPath");
    if (requireFile) {
      if (!outputFiles.has(resolved)) {
        throw new Error("Shell access denied. Only transcription output files from this session can be shown.");
      }
      return resolved;
    }
    if (!outputFiles.has(resolved) && !outputDirs.has(resolved)) {
      throw new Error("Shell access denied. Only transcription output locations from this session can be opened.");
    }
    return resolved;
  }

  return {
    addOutputFiles,
    assertReadableOutputFile,
    assertShellOutputTarget,
    reset,
    hasOutputFile: (filePath) => outputFiles.has(path.resolve(filePath)),
    hasOutputDir: (dirPath) => outputDirs.has(path.resolve(dirPath))
  };
}

module.exports = {
  createOutputAccessStore,
  isMediaFile,
  isOutputFile,
  mediaExtensions,
  outputFormats,
  validatePathArray,
  validateTranscriptionPayload
};
