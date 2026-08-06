const path = require("node:path");

function pythonCandidates(rootDir, platform = process.platform, env = process.env) {
  if (env.WHISPER_PYTHON) {
    return [env.WHISPER_PYTHON];
  }

  if (platform === "win32") {
    return [
      env.WHISPER_CUDA_PYTHON || "C:\\whisper\\torch-env\\Scripts\\python.exe",
      path.join(rootDir, ".release-venv", "Scripts", "python.exe"),
      path.join(rootDir, "venv", "Scripts", "python.exe"),
      "python"
    ];
  }

  return [
    path.join(rootDir, ".release-venv", "bin", "python"),
    path.join(rootDir, "venv", "bin", "python"),
    "python3"
  ];
}

function selectPythonExecutable(rootDir, existsSync, platform = process.platform, env = process.env) {
  if (env.WHISPER_PYTHON) {
    return env.WHISPER_PYTHON;
  }

  const candidates = pythonCandidates(rootDir, platform, env);
  for (const candidate of candidates) {
    if (candidate === "python" || candidate === "python3" || existsSync(candidate)) {
      return candidate;
    }
  }
  return platform === "win32" ? "python" : "python3";
}

module.exports = {
  pythonCandidates,
  selectPythonExecutable
};
