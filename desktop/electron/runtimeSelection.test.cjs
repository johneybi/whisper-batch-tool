const assert = require("node:assert/strict");
const path = require("node:path");
const test = require("node:test");

const {
  pythonCandidates,
  selectPythonExecutable
} = require("./runtimeSelection.cjs");

test("explicit WHISPER_PYTHON overrides runtime discovery", () => {
  const explicit = "D:\\Python\\python.exe";
  assert.deepEqual(
    pythonCandidates("C:\\app", "win32", { WHISPER_PYTHON: explicit }),
    [explicit]
  );
  assert.equal(
    selectPythonExecutable("C:\\app", () => false, "win32", { WHISPER_PYTHON: explicit }),
    explicit
  );
});

test("windows development runtime prefers CUDA torch-env before CPU release venv", () => {
  const root = "C:\\whisper\\whisper-batch-tool";
  const candidates = pythonCandidates(root, "win32", {});

  assert.equal(candidates[0], "C:\\whisper\\torch-env\\Scripts\\python.exe");
  assert.equal(candidates[1], path.join(root, ".release-venv", "Scripts", "python.exe"));
  assert.equal(
    selectPythonExecutable(root, (candidate) => candidate === candidates[0] || candidate === candidates[1], "win32", {}),
    candidates[0]
  );
});

test("WHISPER_CUDA_PYTHON can point to a custom CUDA runtime", () => {
  const custom = "D:\\runtimes\\cuda\\python.exe";
  assert.equal(
    pythonCandidates("C:\\app", "win32", { WHISPER_CUDA_PYTHON: custom })[0],
    custom
  );
});

test("non-windows runtime keeps project venvs before system python", () => {
  const root = "/app";
  assert.deepEqual(
    pythonCandidates(root, "linux", {}),
    [
      path.join(root, ".release-venv", "bin", "python"),
      path.join(root, "venv", "bin", "python"),
      "python3"
    ]
  );
});
