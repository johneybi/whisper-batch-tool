const assert = require("node:assert/strict");
const test = require("node:test");

const {
  createLiveServiceManager,
  resolveLiveProjectRoot,
  validateLiveRunPayload
} = require("./liveService.cjs");

test("live engine root is internal by default and supports an explicit override", () => {
  assert.equal(
    resolveLiveProjectRoot({ WHISPER_LIVE_ENGINE_ROOT: "C:\\tools\\live" }),
    "C:\\tools\\live"
  );
  assert.match(resolveLiveProjectRoot({}), /services[\\/]live-engine$/);
});

test("live payload validation accepts supported YouTube URLs", () => {
  assert.deepEqual(
    validateLiveRunPayload({
      source_url: "https://youtu.be/demo",
      chunk_seconds: 30,
      start_from_beginning: true
    }),
    {
      source_url: "https://youtu.be/demo",
      title: null,
      chunk_seconds: 30,
      start_from_beginning: true
    }
  );
});

test("live payload validation rejects non-YouTube sources and unsafe chunks", () => {
  assert.throws(() => validateLiveRunPayload({ source_url: "https://example.com/live" }), /Only YouTube/);
  assert.throws(
    () => validateLiveRunPayload({ source_url: "https://youtube.com/watch?v=demo", chunk_seconds: 2 }),
    /between 10 and 600/
  );
});

test("readiness explains a missing native runtime", () => {
  const manager = createLiveServiceManager({
    env: { WHISPER_LIVE_ENGINE_ROOT: "C:\\missing-live" },
    platform: "win32",
    existsSync: () => false,
    fetchImpl: async () => { throw new Error("offline"); }
  });
  assert.equal(manager.readiness().ready, false);
  assert.match(manager.readiness().detail, /runtime is missing/);
});
