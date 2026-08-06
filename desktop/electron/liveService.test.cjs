const assert = require("node:assert/strict");
const test = require("node:test");

const {
  createLiveServiceManager,
  resolveLiveProjectRoot,
  validateLiveRunPayload
} = require("./liveService.cjs");

test("live project root prefers explicit configuration", () => {
  assert.equal(
    resolveLiveProjectRoot({ AUTO_NEWS_SCRIPTER_ROOT: "C:\\tools\\live" }, "win32"),
    "C:\\tools\\live"
  );
  assert.equal(resolveLiveProjectRoot({}, "win32"), "E:\\auto-news-scripter");
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
    env: { AUTO_NEWS_SCRIPTER_ROOT: "C:\\missing-live" },
    platform: "win32",
    existsSync: () => false,
    fetchImpl: async () => { throw new Error("offline"); }
  });
  assert.equal(manager.readiness().ready, false);
  assert.match(manager.readiness().detail, /runtime is missing/);
});
