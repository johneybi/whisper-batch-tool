const fs = require("node:fs");
const path = require("node:path");
const { validateLiveRunPayload } = require("./liveService.cjs");

function generateScheduleId() {
  return "sched_" + Date.now().toString(36) + "_" + Math.random().toString(36).substring(2, 7);
}

function validateSchedulePayload(value) {
  if (!value || typeof value !== "object" || Array.isArray(value)) {
    throw new Error("Schedule payload must be an object.");
  }
  const livePayload = validateLiveRunPayload({
    source_url: value.source_url,
    title: value.title,
    chunk_seconds: value.chunk_seconds,
    start_from_beginning: value.start_from_beginning
  });

  const type = value.type === "upcoming" ? "upcoming" : "time";
  let scheduledAt = null;

  if (type === "time") {
    if (!value.scheduled_at) {
      throw new Error("A start date and time is required for scheduled transcription.");
    }
    const parsedDate = new Date(value.scheduled_at);
    if (Number.isNaN(parsedDate.getTime())) {
      throw new Error("Invalid start date and time format.");
    }
    scheduledAt = parsedDate.toISOString();
  }

  const maxMinutes = Number(value.max_minutes ?? 60);
  if (!Number.isInteger(maxMinutes) || maxMinutes < 0 || maxMinutes > 1440) {
    throw new Error("Max recording duration must be an integer between 0 and 1440 minutes.");
  }

  return {
    ...livePayload,
    type,
    scheduled_at: scheduledAt,
    max_minutes: maxMinutes
  };
}

function createSchedulerManager({
  liveService,
  storagePath,
  fsImpl = fs,
  checkIntervalMs = 5000,
  powerSaveBlockerImpl = null,
  onLog = () => undefined
} = {}) {
  let timer = null;
  let powerSaveBlockerId = null;
  let inFlight = false;

  function defaultStoragePath() {
    const projectRoot = liveService?.readiness?.()?.projectRoot;
    if (projectRoot) {
      return path.join(projectRoot, "data", "schedules.json");
    }
    return path.resolve(__dirname, "..", "..", "services", "live-engine", "data", "schedules.json");
  }

  const resolvedStoragePath = storagePath || defaultStoragePath();

  function loadSchedules() {
    try {
      if (!fsImpl.existsSync(resolvedStoragePath)) {
        return [];
      }
      const data = fsImpl.readFileSync(resolvedStoragePath, "utf8");
      const parsed = JSON.parse(data);
      return Array.isArray(parsed) ? parsed : [];
    } catch (err) {
      onLog("Failed to load schedules: " + err.message);
      return [];
    }
  }

  function saveSchedules(schedules) {
    try {
      const dir = path.dirname(resolvedStoragePath);
      if (!fsImpl.existsSync(dir)) {
        fsImpl.mkdirSync(dir, { recursive: true });
      }
      fsImpl.writeFileSync(resolvedStoragePath, JSON.stringify(schedules, null, 2), "utf8");
    } catch (err) {
      onLog("Failed to save schedules: " + err.message);
    }
  }

  function updatePowerSaveBlocker(schedules) {
    if (!powerSaveBlockerImpl) return;
    const hasActiveRunning = schedules.some((s) => s.status === "running");
    if (hasActiveRunning && powerSaveBlockerId === null) {
      try {
        powerSaveBlockerId = powerSaveBlockerImpl.start("prevent-app-suspension");
      } catch (err) {
        onLog("Failed to start powerSaveBlocker: " + err.message);
      }
    } else if (!hasActiveRunning && powerSaveBlockerId !== null) {
      try {
        if (powerSaveBlockerImpl.isStarted(powerSaveBlockerId)) {
          powerSaveBlockerImpl.stop(powerSaveBlockerId);
        }
      } catch (err) {
        onLog("Failed to stop powerSaveBlocker: " + err.message);
      } finally {
        powerSaveBlockerId = null;
      }
    }
  }

  function listSchedules() {
    return loadSchedules();
  }

  function createSchedule(payload) {
    const validated = validateSchedulePayload(payload);
    const schedule = {
      id: generateScheduleId(),
      ...validated,
      status: "pending", // 'pending' | 'running' | 'completed' | 'cancelled' | 'failed'
      live_run_id: null,
      created_at: new Date().toISOString(),
      started_at: null,
      ended_at: null,
      error_message: null
    };

    const schedules = loadSchedules();
    schedules.unshift(schedule);
    saveSchedules(schedules);
    onLog(`예약 등록 완료: ${schedule.title || schedule.source_url} (${schedule.type === "time" ? schedule.scheduled_at : "방송 시작 감지"})`);
    return schedule;
  }

  function cancelSchedule(scheduleId) {
    const schedules = loadSchedules();
    const target = schedules.find((s) => s.id === scheduleId);
    if (!target) {
      throw new Error("Schedule not found: " + scheduleId);
    }
    if (target.status === "running" && target.live_run_id) {
      liveService.stopRun(target.live_run_id).catch(() => undefined);
    }
    target.status = "cancelled";
    target.ended_at = new Date().toISOString();
    saveSchedules(schedules);
    updatePowerSaveBlocker(schedules);
    onLog(`예약 취소됨: ${target.title || target.source_url}`);
    return target;
  }

  function deleteSchedule(scheduleId) {
    let schedules = loadSchedules();
    const target = schedules.find((s) => s.id === scheduleId);
    if (target && target.status === "running" && target.live_run_id) {
      liveService.stopRun(target.live_run_id).catch(() => undefined);
    }
    schedules = schedules.filter((s) => s.id !== scheduleId);
    saveSchedules(schedules);
    updatePowerSaveBlocker(schedules);
    return true;
  }

  async function tick() {
    if (inFlight) return;
    inFlight = true;
    try {
      const schedules = loadSchedules();
      let changed = false;
      const now = new Date();

      let liveRuns = [];
      try {
        liveRuns = await liveService.listRuns();
      } catch {
        // live engine not ready yet or offline
      }

      for (const schedule of schedules) {
        if (schedule.status === "pending") {
          let shouldStart = false;
          if (schedule.type === "time") {
            const scheduledTime = new Date(schedule.scheduled_at);
            if (!Number.isNaN(scheduledTime.getTime()) && now >= scheduledTime) {
              shouldStart = true;
            }
          } else if (schedule.type === "upcoming") {
            // For upcoming streams, we start the live session; the engine will probe and wait for stream
            shouldStart = true;
          }

          if (shouldStart) {
            try {
              const run = await liveService.createRun({
                source_url: schedule.source_url,
                title: schedule.title,
                chunk_seconds: schedule.chunk_seconds,
                start_from_beginning: schedule.start_from_beginning
              });
              schedule.status = "running";
              schedule.live_run_id = run.id;
              schedule.started_at = new Date().toISOString();
              changed = true;
              onLog(`예약 전사 시작됨: ${schedule.title || schedule.source_url} (run_id: ${run.id})`);
            } catch (err) {
              // If live engine has another run active or fails
              onLog(`예약 전사 시작 시도 중 대기/오류: ${err.message}`);
            }
          }
        } else if (schedule.status === "running") {
          const startedAt = schedule.started_at ? new Date(schedule.started_at) : null;
          const maxMinutes = Number(schedule.max_minutes || 0);

          // Check if max recording duration reached
          if (startedAt && maxMinutes > 0) {
            const elapsedMinutes = (now.getTime() - startedAt.getTime()) / (60 * 1000);
            if (elapsedMinutes >= maxMinutes) {
              if (schedule.live_run_id) {
                await liveService.stopRun(schedule.live_run_id).catch(() => undefined);
              }
              schedule.status = "completed";
              schedule.ended_at = new Date().toISOString();
              changed = true;
              onLog(`최대 녹화 시간(${maxMinutes}분) 도달로 예약 전사 종료: ${schedule.title || schedule.source_url}`);
              continue;
            }
          }

          // Check status of the live run in the live engine
          if (schedule.live_run_id) {
            const liveRun = liveRuns.find((r) => r.id === schedule.live_run_id);
            if (liveRun) {
              if (liveRun.status === "completed" || liveRun.status === "stopped") {
                schedule.status = "completed";
                schedule.ended_at = new Date().toISOString();
                changed = true;
              } else if (liveRun.status === "failed") {
                schedule.status = "failed";
                schedule.ended_at = new Date().toISOString();
                schedule.error_message = liveRun.message || "전사 작업 실패";
                changed = true;
              }
            }
          }
        }
      }

      if (changed) {
        saveSchedules(schedules);
        updatePowerSaveBlocker(schedules);
      }
    } catch (err) {
      onLog("Scheduler tick error: " + err.message);
    } finally {
      inFlight = false;
    }
  }

  function start() {
    if (timer) return;
    timer = setInterval(tick, checkIntervalMs);
    tick();
  }

  function stop() {
    if (timer) {
      clearInterval(timer);
      timer = null;
    }
    updatePowerSaveBlocker([]);
  }

  return {
    start,
    stop,
    tick,
    listSchedules,
    createSchedule,
    cancelSchedule,
    deleteSchedule,
    loadSchedules,
    saveSchedules
  };
}

module.exports = {
  generateScheduleId,
  validateSchedulePayload,
  createSchedulerManager
};
