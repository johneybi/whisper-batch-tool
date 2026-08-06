const assert = require("node:assert/strict");
const fs = require("node:fs");
const os = require("node:os");
const path = require("node:path");
const test = require("node:test");

const { discoverMediaPaths } = require("./mediaDiscovery.cjs");

function isMediaFile(filePath) {
  return [".wav", ".mp4", ".mkv"].includes(path.extname(filePath).toLowerCase());
}

async function withTempDir(callback) {
  const root = await fs.promises.mkdtemp(path.join(os.tmpdir(), "media-discovery-"));
  try {
    return await callback(root);
  } finally {
    await fs.promises.rm(root, { recursive: true, force: true });
  }
}

test("discovers supported files asynchronously and reports skipped reasons", async () => {
  await withTempDir(async (root) => {
    const nested = path.join(root, "nested");
    await fs.promises.mkdir(nested);
    await fs.promises.writeFile(path.join(root, "clip.wav"), "");
    await fs.promises.writeFile(path.join(root, "notes.txt"), "");
    await fs.promises.writeFile(path.join(nested, "video.MKV"), "");

    const result = await discoverMediaPaths([root], {
      fsModule: fs,
      isMediaFile,
      recursive: true,
      limits: { maxFiles: 10, maxDepth: 5, timeoutMs: 30000, yieldEvery: 1 }
    });

    assert.deepEqual(result.files.map((file) => file.name), ["clip.wav", "video.MKV"]);
    assert.equal(result.skippedReasons.unsupported, 1);
    assert.equal(result.canceled, false);
  });
});

test("respects max file and max depth limits", async () => {
  await withTempDir(async (root) => {
    const nested = path.join(root, "nested");
    await fs.promises.mkdir(nested);
    await fs.promises.writeFile(path.join(root, "a.wav"), "");
    await fs.promises.writeFile(path.join(root, "b.wav"), "");
    await fs.promises.writeFile(path.join(nested, "deep.wav"), "");

    const maxFilesResult = await discoverMediaPaths([root], {
      fsModule: fs,
      isMediaFile,
      recursive: true,
      limits: { maxFiles: 1, maxDepth: 5, timeoutMs: 30000, yieldEvery: 1 }
    });

    assert.equal(maxFilesResult.files.length, 1);
    assert.equal(maxFilesResult.truncated, true);
    assert.ok(maxFilesResult.skippedReasons.maxFiles >= 1);

    const maxDepthResult = await discoverMediaPaths([root], {
      fsModule: fs,
      isMediaFile,
      recursive: true,
      limits: { maxFiles: 10, maxDepth: 0, timeoutMs: 30000, yieldEvery: 1 }
    });

    assert.deepEqual(maxDepthResult.files.map((file) => file.name), ["a.wav", "b.wav"]);
    assert.equal(maxDepthResult.skippedReasons.maxDepth, 1);
  });
});

test("skips symlinks to avoid recursive loops", async () => {
  await withTempDir(async (root) => {
    await fs.promises.writeFile(path.join(root, "clip.wav"), "");
    const link = path.join(root, "loop");
    try {
      await fs.promises.symlink(root, link, "junction");
    } catch {
      return;
    }

    const result = await discoverMediaPaths([root], {
      fsModule: fs,
      isMediaFile,
      recursive: true,
      limits: { maxFiles: 10, maxDepth: 5, timeoutMs: 30000, yieldEvery: 1 }
    });

    assert.deepEqual(result.files.map((file) => file.name), ["clip.wav"]);
    assert.ok(result.skippedReasons.symlink >= 1);
  });
});

test("supports cancellation through AbortSignal", async () => {
  await withTempDir(async (root) => {
    for (let index = 0; index < 50; index += 1) {
      await fs.promises.writeFile(path.join(root, `${index}.wav`), "");
    }
    const controller = new AbortController();
    setImmediate(() => controller.abort());

    const result = await discoverMediaPaths([root], {
      fsModule: fs,
      isMediaFile,
      recursive: true,
      signal: controller.signal,
      limits: { maxFiles: 100, maxDepth: 5, timeoutMs: 30000, yieldEvery: 1 }
    });

    assert.equal(result.canceled, true);
    assert.ok(result.skippedReasons.canceled >= 1);
  });
});
