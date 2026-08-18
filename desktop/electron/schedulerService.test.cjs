const assert = require("node:assert/strict");
const test = require("node:test");
const {
  validateSchedulePayload,
  createSchedulerManager
} = require("./schedulerService.cjs");

test("validateSchedulePayload validates time schedule correctly", () => {
  const future = new Date(Date.now() + 60000).toISOString();
  const payload = {
    source_url: "https://www.youtube.com/watch?v=dQw4w9WgXcQ",
    type: "time",
    scheduled_at: future,
    max_minutes: 30,
    chunk_seconds: 10,
    start_from_beginning: true
  };
  const validated = validateSchedulePayload(payload);
  assert.equal(validated.source_url, "https://www.youtube.com/watch?v=dQw4w9WgXcQ");
  assert.equal(validated.type, "time");
  assert.equal(validated.scheduled_at, future);
  assert.equal(validated.max_minutes, 30);
  assert.equal(validated.chunk_seconds, 10);
});

test("validateSchedulePayload rejects missing scheduled_at for time type", () => {
  assert.throws(() => {
    validateSchedulePayload({
      source_url: "https://www.youtube.com/watch?v=dQw4w9WgXcQ",
      type: "time"
    });
  }, /start date and time is required/);
});

test("validateSchedulePayload accepts upcoming type without scheduled_at", () => {
  const validated = validateSchedulePayload({
    source_url: "https://www.youtube.com/watch?v=dQw4w9WgXcQ",
    type: "upcoming",
    max_minutes: 60
  });
  assert.equal(validated.type, "upcoming");
  assert.equal(validated.scheduled_at, null);
});

test("createSchedulerManager manages lifecycle correctly", async () => {
  const mockStorage = {};
  const mockFs = {
    existsSync: (p) => Boolean(mockStorage[p]),
    readFileSync: (p) => mockStorage[p] || "[]",
    writeFileSync: (p, data) => { mockStorage[p] = data; },
    mkdirSync: () => undefined
  };

  let runStarted = null;
  const mockLiveService = {
    createRun: async (payload) => {
      runStarted = payload;
      return { id: "live_run_123" };
    },
    listRuns: async () => [{ id: "live_run_123", status: "capturing" }],
    stopRun: async () => ({ id: "live_run_123", status: "stopped" })
  };

  const manager = createSchedulerManager({
    liveService: mockLiveService,
    storagePath: "dummy/schedules.json",
    fsImpl: mockFs,
    onLog: () => undefined
  });

  const created = manager.createSchedule({
    source_url: "https://www.youtube.com/watch?v=dQw4w9WgXcQ",
    type: "time",
    scheduled_at: new Date(Date.now() - 1000).toISOString(),
    max_minutes: 60,
    chunk_seconds: 10
  });

  assert.equal(created.status, "pending");
  assert.equal(manager.listSchedules().length, 1);

  // Tick should trigger start
  await manager.tick();
  const schedulesAfterTick = manager.listSchedules();
  assert.equal(schedulesAfterTick[0].status, "running");
  assert.equal(schedulesAfterTick[0].live_run_id, "live_run_123");
  assert.ok(runStarted);

  // Cancel schedule
  manager.cancelSchedule(created.id);
  assert.equal(manager.listSchedules()[0].status, "cancelled");

  // Delete schedule
  manager.deleteSchedule(created.id);
  assert.equal(manager.listSchedules().length, 0);
});
