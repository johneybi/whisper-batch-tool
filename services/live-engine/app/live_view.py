from __future__ import annotations

import json
import logging
import queue
import threading
import uuid
from contextlib import asynccontextmanager
from concurrent.futures import Future, ThreadPoolExecutor
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Iterator

from fastapi import FastAPI, HTTPException
from fastapi.responses import HTMLResponse, StreamingResponse
from pydantic import BaseModel, Field

from .config import settings
from .manual_transcribe import StreamMetadata, transcribe_url
from .transcriber import TranscriptSegment, format_segments


LOGGER = logging.getLogger(__name__)
ACTIVE_CAPTURE_LIMIT = 2


def utc_now() -> str:
    return datetime.now(timezone.utc).isoformat()


@dataclass
class LiveRun:
    id: str
    source_url: str
    title_override: str | None
    chunk_seconds: int
    start_from_beginning: bool = True
    status: str = "queued"
    message: str = "캡처 슬롯을 기다리고 있습니다."
    title: str = "방송 정보 확인 중"
    author: str = "YouTube"
    is_live: bool | None = None
    transcript_path: str | None = None
    transcript: str = ""
    captured_seconds: float = 0.0
    chunk_count: int = 0
    sequence: int = 0
    created_at: str = field(default_factory=utc_now)
    updated_at: str = field(default_factory=utc_now)
    stop_event: threading.Event = field(
        default_factory=threading.Event,
        repr=False,
    )

    def snapshot(self) -> dict:
        return {
            "id": self.id,
            "source_url": self.source_url,
            "start_from_beginning": self.start_from_beginning,
            "title": self.title,
            "author": self.author,
            "is_live": self.is_live,
            "status": self.status,
            "message": self.message,
            "transcript_path": self.transcript_path,
            "transcript": self.transcript,
            "captured_seconds": self.captured_seconds,
            "chunk_count": self.chunk_count,
            "sequence": self.sequence,
            "created_at": self.created_at,
            "updated_at": self.updated_at,
        }


class EventBroker:
    def __init__(self) -> None:
        self._lock = threading.Lock()
        self._subscribers: set[queue.Queue[dict]] = set()

    def subscribe(self) -> queue.Queue[dict]:
        subscriber: queue.Queue[dict] = queue.Queue(maxsize=200)
        with self._lock:
            self._subscribers.add(subscriber)
        return subscriber

    def unsubscribe(self, subscriber: queue.Queue[dict]) -> None:
        with self._lock:
            self._subscribers.discard(subscriber)

    def publish(self, event: dict) -> None:
        with self._lock:
            subscribers = list(self._subscribers)
        for subscriber in subscribers:
            try:
                subscriber.put_nowait(event)
            except queue.Full:
                try:
                    subscriber.get_nowait()
                except queue.Empty:
                    pass
                try:
                    subscriber.put_nowait(event)
                except queue.Full:
                    pass


class LiveCoordinator:
    def __init__(self, *, max_captures: int = ACTIVE_CAPTURE_LIMIT) -> None:
        self._lock = threading.RLock()
        self._runs: dict[str, LiveRun] = {}
        self._futures: dict[str, Future] = {}
        self._executor = ThreadPoolExecutor(
            max_workers=max_captures,
            thread_name_prefix="live-capture",
        )
        self.events = EventBroker()

    def create_run(
        self,
        *,
        source_url: str,
        title: str | None,
        chunk_seconds: int,
        start_from_beginning: bool = True,
    ) -> dict:
        run = LiveRun(
            id=uuid.uuid4().hex[:12],
            source_url=source_url,
            title_override=title,
            chunk_seconds=chunk_seconds,
            start_from_beginning=start_from_beginning,
        )
        with self._lock:
            self._runs[run.id] = run
            self._futures[run.id] = self._executor.submit(
                self._execute,
                run.id,
            )
            snapshot = run.snapshot()
        self.events.publish({"type": "run", "run": snapshot})
        return snapshot

    def list_runs(self) -> list[dict]:
        with self._lock:
            runs = [run.snapshot() for run in self._runs.values()]
        return sorted(runs, key=lambda item: item["created_at"], reverse=True)

    def get_run(self, run_id: str) -> dict:
        with self._lock:
            run = self._runs.get(run_id)
            if run is None:
                raise KeyError(run_id)
            return run.snapshot()

    def stop_run(self, run_id: str) -> dict:
        with self._lock:
            run = self._runs.get(run_id)
            if run is None:
                raise KeyError(run_id)
            run.stop_event.set()
            if run.status == "queued":
                future = self._futures.get(run_id)
                if future and future.cancel():
                    self._update_locked(
                        run,
                        status="stopped",
                        message="대기 중인 전사를 취소했습니다.",
                    )
            elif run.status not in {"completed", "failed", "stopped"}:
                self._update_locked(
                    run,
                    status="stopping",
                    message="현재 청크를 정리하고 있습니다.",
                )
            snapshot = run.snapshot()
        self.events.publish({"type": "run", "run": snapshot})
        return snapshot

    def shutdown(self, *, wait: bool = True) -> None:
        with self._lock:
            for run in self._runs.values():
                run.stop_event.set()
        self._executor.shutdown(wait=wait, cancel_futures=True)

    def _execute(self, run_id: str) -> None:
        with self._lock:
            run = self._runs[run_id]
            if run.stop_event.is_set():
                self._publish_update(
                    run,
                    status="stopped",
                    message="전사를 시작하지 않았습니다.",
                )
                return
            self._publish_update(
                run,
                status="probing",
                message="방송 정보를 확인하고 있습니다.",
            )

        try:
            transcript_path = transcribe_url(
                source_url=run.source_url,
                title_override=run.title_override,
                output_dir=settings.knowledge_dir,
                chunk_seconds=run.chunk_seconds,
                max_chunks=0,
                stop_event=run.stop_event,
                start_from_beginning=run.start_from_beginning,
                on_metadata=lambda metadata, path: self._on_metadata(
                    run,
                    metadata,
                    path,
                ),
                on_progress=lambda path, segments, elapsed, chunks: (
                    self._on_progress(
                        run,
                        path,
                        segments,
                        elapsed,
                        chunks,
                    )
                ),
                on_status=lambda status, message: self._publish_update(
                    run,
                    status=status,
                    message=message,
                ),
            )
            final_status = (
                "stopped" if run.stop_event.is_set() else "completed"
            )
            final_message = (
                "사용자 요청으로 전사를 멈췄습니다."
                if final_status == "stopped"
                else "전사가 끝났습니다."
            )
            self._publish_update(
                run,
                status=final_status,
                message=final_message,
                transcript_path=str(transcript_path),
            )
        except Exception as exc:
            LOGGER.exception("live transcription failed run_id=%s", run.id)
            self._publish_update(
                run,
                status="failed",
                message=str(exc),
            )

    def _on_metadata(
        self,
        run: LiveRun,
        metadata: StreamMetadata,
        transcript_path: Path,
    ) -> None:
        self._publish_update(
            run,
            title=run.title_override or metadata.title,
            author=metadata.author,
            is_live=metadata.is_live,
            transcript_path=str(transcript_path),
        )

    def _on_progress(
        self,
        run: LiveRun,
        transcript_path: Path,
        segments: list[TranscriptSegment],
        elapsed: float,
        chunks: int,
    ) -> None:
        self._publish_update(
            run,
            status="transcribing",
            message="새 전사 내용이 도착했습니다.",
            transcript_path=str(transcript_path),
            transcript=format_segments(segments),
            captured_seconds=elapsed,
            chunk_count=chunks,
        )

    def _publish_update(self, run: LiveRun, **changes) -> None:
        with self._lock:
            self._update_locked(run, **changes)
            snapshot = run.snapshot()
        self.events.publish({"type": "run", "run": snapshot})

    @staticmethod
    def _update_locked(run: LiveRun, **changes) -> None:
        for key, value in changes.items():
            setattr(run, key, value)
        run.sequence += 1
        run.updated_at = utc_now()


class CreateRunRequest(BaseModel):
    source_url: str = Field(min_length=8, max_length=2000)
    title: str | None = Field(default=None, max_length=200)
    chunk_seconds: int = Field(default=30, ge=10, le=600)
    start_from_beginning: bool = True


coordinator = LiveCoordinator()


@asynccontextmanager
async def lifespan(_app: FastAPI):
    yield
    coordinator.shutdown()


app = FastAPI(title="Live Transcript Viewer", lifespan=lifespan)


@app.get("/", response_class=HTMLResponse)
def dashboard() -> str:
    return DASHBOARD_HTML


@app.get("/api/runs")
def list_runs() -> list[dict]:
    return coordinator.list_runs()


@app.get("/api/runs/{run_id}")
def get_run(run_id: str) -> dict:
    try:
        return coordinator.get_run(run_id)
    except KeyError as exc:
        raise HTTPException(status_code=404, detail="Run not found") from exc


@app.post("/api/runs", status_code=201)
def create_run(request: CreateRunRequest) -> dict:
    if not request.source_url.startswith(("https://", "http://")):
        raise HTTPException(status_code=400, detail="A valid URL is required")
    return coordinator.create_run(
        source_url=request.source_url,
        title=request.title,
        chunk_seconds=request.chunk_seconds,
        start_from_beginning=request.start_from_beginning,
    )


@app.post("/api/runs/{run_id}/stop")
def stop_run(run_id: str) -> dict:
    try:
        return coordinator.stop_run(run_id)
    except KeyError as exc:
        raise HTTPException(status_code=404, detail="Run not found") from exc


@app.get("/api/events")
def stream_events() -> StreamingResponse:
    subscriber = coordinator.events.subscribe()

    def generate() -> Iterator[str]:
        try:
            yield _sse({"type": "snapshot", "runs": coordinator.list_runs()})
            while True:
                try:
                    event = subscriber.get(timeout=15)
                    run = event.get("run") or {}
                    event_id = f"{run.get('id', 'all')}:{run.get('sequence', 0)}"
                    yield _sse(event, event_id=event_id)
                except queue.Empty:
                    yield ": keep-alive\n\n"
        finally:
            coordinator.events.unsubscribe(subscriber)

    return StreamingResponse(
        generate(),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "X-Accel-Buffering": "no",
        },
    )


def _sse(payload: dict, *, event_id: str | None = None) -> str:
    prefix = f"id: {event_id}\n" if event_id else ""
    return prefix + "data: " + json.dumps(
        payload,
        ensure_ascii=False,
    ) + "\n\n"


DASHBOARD_HTML = r"""<!doctype html>
<html lang="ko">
<head>
  <meta charset="utf-8">
  <meta name="viewport" content="width=device-width, initial-scale=1">
  <title>Live Transcript</title>
  <style>
    :root { color-scheme: dark; font-family: Inter, Pretendard, system-ui, sans-serif; }
    * { box-sizing: border-box; }
    body { margin: 0; background: #0b0d10; color: #e9edf2; }
    header { position: sticky; top: 0; z-index: 2; padding: 22px clamp(18px, 4vw, 56px); background: rgba(11,13,16,.94); border-bottom: 1px solid #242932; backdrop-filter: blur(12px); }
    h1 { margin: 0 0 5px; font-size: clamp(21px, 3vw, 30px); letter-spacing: -.04em; }
    .lead { color: #939eae; font-size: 14px; }
    form { display: grid; grid-template-columns: minmax(250px, 1fr) 110px 100px auto; gap: 9px; margin-top: 18px; max-width: 1040px; }
    input, select, button { min-height: 42px; border-radius: 9px; border: 1px solid #303641; font: inherit; }
    input, select { padding: 0 13px; color: #f6f8fb; background: #15191f; outline: none; }
    input:focus { border-color: #6ba5ff; box-shadow: 0 0 0 3px #1f4d8b55; }
    button { padding: 0 16px; color: #07101d; background: #77aaff; border-color: #77aaff; font-weight: 700; cursor: pointer; }
    button.secondary { min-height: 32px; padding: 0 10px; color: #d8dee8; background: transparent; border-color: #3b424e; font-size: 12px; }
    main { padding: 24px clamp(18px, 4vw, 56px) 60px; }
    #empty { padding: 70px 20px; color: #6f7988; text-align: center; border: 1px dashed #2d333d; border-radius: 14px; }
    #runs { display: grid; grid-template-columns: repeat(auto-fit, minmax(min(100%, 430px), 1fr)); gap: 18px; }
    article { min-width: 0; overflow: hidden; background: #12161b; border: 1px solid #282e37; border-radius: 14px; box-shadow: 0 14px 45px #0005; }
    .card-head { padding: 16px 18px 13px; border-bottom: 1px solid #252b33; }
    .topline { display: flex; align-items: center; justify-content: space-between; gap: 12px; }
    h2 { margin: 8px 0 2px; overflow: hidden; font-size: 17px; white-space: nowrap; text-overflow: ellipsis; }
    .author, .meta { color: #84909f; font-size: 12px; }
    .status { display: inline-flex; align-items: center; gap: 7px; font-size: 12px; color: #aeb8c6; }
    .dot { width: 8px; height: 8px; border-radius: 50%; background: #7a8491; }
    .active .dot { background: #44d18e; box-shadow: 0 0 0 4px #44d18e20; }
    .failed .dot { background: #ff6f6f; }
    .queued .dot { background: #ffbd61; }
    pre { height: 420px; margin: 0; padding: 18px; overflow: auto; color: #dce3ec; background: #0e1115; font: 14px/1.75 "Cascadia Mono", "Noto Sans Mono", monospace; white-space: pre-wrap; overflow-wrap: anywhere; }
    .placeholder { color: #66717f; }
    @media (max-width: 650px) { form { grid-template-columns: 1fr 85px; } form input:first-child { grid-column: 1 / -1; } pre { height: 52vh; } }
  </style>
</head>
<body>
  <header>
    <h1>Live Transcript</h1>
    <div class="lead">라이브는 방송 시작점부터, 동시에 2개까지 캡처하고 하나의 GPU 모델로 전사합니다.</div>
    <form id="start-form">
      <input id="url" type="url" required placeholder="YouTube 라이브 또는 영상 URL">
      <select id="start-mode" title="라이브 시작 위치">
        <option value="beginning">처음부터</option>
        <option value="now">현재부터</option>
      </select>
      <input id="chunk" type="number" min="10" max="600" value="30" title="청크 길이(초)">
      <button type="submit">전사 시작</button>
    </form>
  </header>
  <main>
    <div id="empty">URL을 넣으면 실시간 전사가 여기에 나타납니다.</div>
    <section id="runs"></section>
  </main>
  <script>
    const runs = new Map();
    const container = document.querySelector('#runs');
    const empty = document.querySelector('#empty');
    const transcriptScrollState = new Map();
    const transcriptManualScroll = new Map();
    const esc = value => String(value ?? '').replace(/[&<>"']/g, c => ({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}[c]));
    const terminal = new Set(['completed', 'failed', 'stopped']);
    const active = new Set(['capturing', 'transcribing', 'draining', 'probing', 'reconnecting', 'stopping']);
    function render() {
      // Re-rendering the cards replaces each <pre>. Remember the user's
      // position first so polling does not yank them away from older text.
      document.querySelectorAll('#runs article').forEach(article => {
        const pre = article.querySelector('pre');
        if (!pre) return;
        const distanceFromBottom = pre.scrollHeight - pre.scrollTop - pre.clientHeight;
        transcriptScrollState.set(article.id.slice(4), {
          top: pre.scrollTop,
          followTail: distanceFromBottom <= 24,
        });
      });
      const values = [...runs.values()].sort((a,b) => b.created_at.localeCompare(a.created_at));
      empty.hidden = values.length > 0;
      container.innerHTML = values.map(run => {
        const kind = run.status === 'failed' ? 'failed' : active.has(run.status) ? 'active' : run.status === 'queued' ? 'queued' : '';
        const elapsed = new Date(Math.max(0, run.captured_seconds) * 1000).toISOString().slice(11,19);
        const body = run.transcript || '아직 도착한 전사 내용이 없습니다.';
        return `<article id="run-${esc(run.id)}">
          <div class="card-head">
            <div class="topline">
              <span class="status ${kind}"><i class="dot"></i>${esc(run.message)}</span>
              ${terminal.has(run.status) ? '' : `<button class="secondary" onclick="stopRun('${esc(run.id)}')">중지</button>`}
            </div>
            <h2 title="${esc(run.title)}">${esc(run.title)}</h2>
            <div class="author">${esc(run.author)} · ${elapsed} · ${run.chunk_count}개 청크</div>
          </div>
          <pre class="${run.transcript ? '' : 'placeholder'}">${esc(body)}</pre>
        </article>`;
      }).join('');
      values.forEach(run => {
        const pre = document.querySelector(`#run-${run.id} pre`);
        if (!pre || !active.has(run.status)) return;
        const previous = transcriptScrollState.get(run.id);
        if (!previous || (!transcriptManualScroll.get(run.id) && previous.followTail)) {
          pre.scrollTop = pre.scrollHeight;
        } else {
          pre.scrollTop = Math.min(previous.top, pre.scrollHeight);
        }
        if (!pre.dataset.scrollBound) {
          pre.dataset.scrollBound = '1';
          pre.addEventListener('scroll', () => {
            const distanceFromBottom = pre.scrollHeight - pre.scrollTop - pre.clientHeight;
            if (distanceFromBottom > 24) transcriptManualScroll.set(run.id, true);
            else transcriptManualScroll.delete(run.id);
          }, {passive: true});
        }
      });
    }
    function accept(run) {
      const previous = runs.get(run.id);
      if (!previous || run.sequence >= previous.sequence) {
        runs.set(run.id, run);
        render();
      }
    }
    async function load() {
      (await (await fetch('/api/runs')).json()).forEach(accept);
    }
    document.querySelector('#start-form').addEventListener('submit', async event => {
      event.preventDefault();
      const button = event.target.querySelector('button');
      button.disabled = true;
      try {
        const response = await fetch('/api/runs', {
          method: 'POST',
          headers: {'Content-Type': 'application/json'},
          body: JSON.stringify({
            source_url: document.querySelector('#url').value,
            chunk_seconds: Number(document.querySelector('#chunk').value),
            start_from_beginning: document.querySelector('#start-mode').value === 'beginning'
          })
        });
        if (!response.ok) throw new Error((await response.json()).detail || '시작하지 못했습니다.');
        accept(await response.json());
        document.querySelector('#url').value = '';
      } catch (error) { alert(error.message); }
      finally { button.disabled = false; }
    });
    async function stopRun(id) {
      const response = await fetch(`/api/runs/${id}/stop`, {method: 'POST'});
      if (response.ok) accept(await response.json());
    }
    const events = new EventSource('/api/events');
    events.onmessage = event => {
      const payload = JSON.parse(event.data);
      if (payload.type === 'snapshot') payload.runs.forEach(accept);
      if (payload.type === 'run') accept(payload.run);
    };
    load();
  </script>
</body>
</html>"""
