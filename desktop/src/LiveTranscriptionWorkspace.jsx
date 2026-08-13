import React, { useCallback, useEffect, useLayoutEffect, useMemo, useRef, useState } from "react";
import { Clock3, Loader2, Play, Radio, RefreshCw, Square, Wifi } from "lucide-react";

import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { cn } from "@/lib/utils";

const ACTIVE_STATES = new Set(["queued", "probing", "capturing", "transcribing", "draining", "reconnecting", "stopping"]);
const TERMINAL_STATES = new Set(["completed", "failed", "stopped"]);

function durationLabel(seconds) {
  const safe = Math.max(0, Number(seconds) || 0);
  const hours = Math.floor(safe / 3600);
  const minutes = Math.floor((safe % 3600) / 60);
  const remaining = Math.floor(safe % 60);
  return [hours, minutes, remaining].map((value) => String(value).padStart(2, "0")).join(":");
}

function statusLabel(run) {
  return run.message || {
    queued: "대기 중",
    probing: "방송 확인 중",
    capturing: "캡처 중",
    transcribing: "전사 중",
    reconnecting: "재연결 중",
    completed: "완료",
    failed: "실패",
    stopped: "중지됨"
  }[run.status] || run.status;
}

function statusHint(run) {
  if (run.transcript) return "전사문이 들어오고 있습니다. 아래 창에서 내용을 확인하세요.";
  if (run.status === "capturing") return "오디오를 모으는 중입니다. 첫 청크 수집 후 전사문이 표시됩니다.";
  if (run.status === "transcribing") return "수집한 오디오를 Whisper가 전사하고 있습니다.";
  if (run.status === "probing") return "YouTube 방송 상태와 오디오 소스를 확인하고 있습니다.";
  if (run.status === "queued") return "다른 전사 작업이 끝날 때까지 대기 중입니다.";
  if (run.status === "reconnecting") return "방송 연결을 다시 시도하고 있습니다.";
  return statusLabel(run);
}

function updatedAtLabel(value) {
  if (!value) return "-";
  const date = new Date(value);
  if (Number.isNaN(date.getTime())) return "-";
  return new Intl.DateTimeFormat("ko-KR", { hour: "2-digit", minute: "2-digit", second: "2-digit" }).format(date);
}

export function LiveTranscriptionWorkspace({ api, onLog }) {
  const [service, setService] = useState({ ready: false, running: false, loading: true, detail: "실시간 엔진 시작 중..." });
  const [runs, setRuns] = useState([]);
  const [sourceUrl, setSourceUrl] = useState("");
  const [chunkSeconds, setChunkSeconds] = useState(30);
  const [startFromBeginning, setStartFromBeginning] = useState(true);
  const [submitting, setSubmitting] = useState(false);
  const [error, setError] = useState("");
  const transcriptRefs = useRef(new Map());
  const transcriptScrollState = useRef(new Map());

  const activeCount = useMemo(() => runs.filter((run) => ACTIVE_STATES.has(run.status)).length, [runs]);

  const captureTranscriptScroll = useCallback(() => {
    transcriptRefs.current.forEach((element, runId) => {
      if (!element) return;
      const distanceFromBottom = element.scrollHeight - element.scrollTop - element.clientHeight;
      transcriptScrollState.current.set(runId, {
        scrollTop: element.scrollTop,
        followTail: distanceFromBottom <= 24
      });
    });
  }, []);

  useLayoutEffect(() => {
    runs.forEach((run) => {
      const element = transcriptRefs.current.get(run.id);
      if (!element) return;
      const previous = transcriptScrollState.current.get(run.id);
      if (!previous || previous.followTail) {
        element.scrollTop = element.scrollHeight;
        return;
      }
      element.scrollTop = Math.min(previous.scrollTop, Math.max(0, element.scrollHeight - element.clientHeight));
    });
  }, [runs]);

  const refreshRuns = useCallback(async () => {
    try {
      const nextRuns = await api.listLiveRuns();
      captureTranscriptScroll();
      setRuns(nextRuns);
      setError("");
    } catch (refreshError) {
      setError(refreshError.message);
    }
  }, [api, captureTranscriptScroll]);

  useEffect(() => {
    let disposed = false;
    let timer;
    api.initializeLiveService()
      .then((state) => {
        if (disposed) return;
        setService({ ...state, loading: false, detail: state.detail || (state.running ? "실시간 엔진 준비 완료" : "실시간 엔진을 시작하지 못했습니다.") });
        if (!state.ready) return;
        refreshRuns();
        timer = window.setInterval(refreshRuns, 1500);
      })
      .catch((initializeError) => {
        if (disposed) return;
        setService({ ready: false, running: false, loading: false, detail: initializeError.message });
        setError(initializeError.message);
      });
    return () => {
      disposed = true;
      if (timer) window.clearInterval(timer);
    };
  }, [api, refreshRuns]);

  async function startRun(event) {
    event.preventDefault();
    setSubmitting(true);
    setError("");
    try {
      const run = await api.startLiveTranscription({
        source_url: sourceUrl,
        chunk_seconds: Number(chunkSeconds),
        start_from_beginning: startFromBeginning
      });
      captureTranscriptScroll();
      setRuns((previous) => [run, ...previous.filter((item) => item.id !== run.id)]);
      setSourceUrl("");
      onLog?.(`실시간 전사 시작: ${run.title || run.source_url}`, "success");
    } catch (startError) {
      setError(startError.message);
      onLog?.(`실시간 전사 시작 실패: ${startError.message}`, "error");
    } finally {
      setSubmitting(false);
    }
  }

  async function stopRun(runId) {
    try {
      const run = await api.stopLiveTranscription(runId);
      captureTranscriptScroll();
      setRuns((previous) => previous.map((item) => item.id === run.id ? run : item));
      onLog?.(`실시간 전사 중지 요청: ${run.title}`, "warn");
    } catch (stopError) {
      setError(stopError.message);
    }
  }

  return (
    <>
      <div className="grid min-h-0 grid-cols-[420px_minmax(0,1fr)] gap-3 p-3">
        <Card className="flex min-h-0 flex-col">
          <CardHeader>
            <div className="flex items-start justify-between gap-3">
              <div>
                <CardTitle className="flex items-center gap-2"><Radio className="h-5 w-5 text-primary" /> 실시간 전사</CardTitle>
                <p className="mt-2 text-sm leading-6 text-muted-foreground">YouTube 라이브 또는 일반 영상 URL을 연속 청크로 전사합니다.</p>
              </div>
              <Badge variant={service.ready ? "success" : "outline"}>
                {service.loading ? <Loader2 className="h-3 w-3 animate-spin" /> : <Wifi className="h-3 w-3" />}
                {service.ready ? "Engine ready" : "Setup needed"}
              </Badge>
            </div>
          </CardHeader>
          <CardContent className="flex min-h-0 flex-1 flex-col gap-6">
            <form className="space-y-5" onSubmit={startRun}>
              <div className="space-y-2">
                <Label htmlFor="live-source-url">YouTube URL</Label>
                <Input
                  id="live-source-url"
                  type="url"
                  required
                  value={sourceUrl}
                  onChange={(event) => setSourceUrl(event.target.value)}
                  placeholder="https://www.youtube.com/watch?v=..."
                />
              </div>
              <fieldset className="space-y-3">
                <legend className="text-sm font-semibold">시작 위치</legend>
                <div className="grid grid-cols-2 gap-2">
                  <Button type="button" variant={startFromBeginning ? "default" : "outline"} onClick={() => setStartFromBeginning(true)}>처음부터</Button>
                  <Button type="button" variant={!startFromBeginning ? "default" : "outline"} onClick={() => setStartFromBeginning(false)}>현재부터</Button>
                </div>
              </fieldset>
              <div className="space-y-2">
                <Label htmlFor="live-chunk-seconds">청크 길이</Label>
                <select
                  id="live-chunk-seconds"
                  className="flex h-10 w-full rounded-lg border border-input bg-background px-3 py-2 text-sm"
                  value={chunkSeconds}
                  onChange={(event) => setChunkSeconds(Number(event.target.value))}
                >
                  <option value={15}>15초 · 빠른 갱신</option>
                  <option value={30}>30초 · 권장</option>
                  <option value={60}>60초 · 긴 문맥</option>
                </select>
              </div>
              <Button className="h-12 w-full text-base font-bold" disabled={!service.ready || submitting || !sourceUrl.trim()} type="submit">
                {submitting ? <Loader2 className="h-5 w-5 animate-spin" /> : <Play className="h-5 w-5" fill="currentColor" />}
                전사 시작
              </Button>
            </form>

            <div className={cn("rounded-lg border p-4 text-sm leading-6", service.ready ? "border-emerald-200 bg-emerald-50 text-emerald-800" : "border-amber-200 bg-amber-50 text-amber-900")}>
              <p className="font-semibold">{service.detail}</p>
              {service.projectRoot && <p className="mt-1 break-all text-xs opacity-80">{service.projectRoot}</p>}
            </div>
            {error && <div className="rounded-lg border border-destructive/30 bg-destructive/5 p-4 text-sm text-destructive">{error}</div>}
            <p className="mt-auto text-xs leading-5 text-muted-foreground">일반 파일 전사와 실시간 전사는 GPU 메모리 충돌을 막기 위해 동시에 시작할 수 없습니다.</p>
          </CardContent>
        </Card>

        <Card className="flex min-h-0 flex-col">
          <CardHeader className="shrink-0">
            <div className="flex items-center justify-between">
              <div>
                <CardTitle>방송 전사 현황</CardTitle>
                <p className="mt-2 text-sm text-muted-foreground">{activeCount}개 실행 중 · 최대 2개 동시 캡처</p>
              </div>
              <Button size="sm" variant="outline" onClick={refreshRuns} disabled={!service.ready}><RefreshCw className="h-4 w-4" /> 새로고침</Button>
            </div>
          </CardHeader>
          <CardContent className="min-h-0 flex-1 overflow-auto">
            {runs.length === 0 ? (
              <div className="grid h-full place-items-center rounded-lg border border-dashed text-center text-muted-foreground">
                <div><Radio className="mx-auto mb-3 h-9 w-9" /><p className="font-semibold text-foreground">진행 중인 방송이 없습니다.</p><p className="mt-2 text-sm">왼쪽에 YouTube URL을 입력해 시작하세요.</p></div>
              </div>
            ) : (
              <div className="grid grid-cols-2 gap-3">
                {runs.map((run) => (
                  <article className="overflow-hidden rounded-xl border bg-card" key={run.id}>
                    <div className="border-b p-4">
                      <div className="flex items-center justify-between gap-3">
                        <Badge variant={run.status === "failed" ? "destructive" : ACTIVE_STATES.has(run.status) ? "success" : "secondary"}>
                          {ACTIVE_STATES.has(run.status) && <Loader2 className="h-3 w-3 animate-spin" />}
                          {statusLabel(run)}
                        </Badge>
                        {!TERMINAL_STATES.has(run.status) && <Button size="sm" variant="outline" onClick={() => stopRun(run.id)}><Square className="h-3.5 w-3.5" /> 중지</Button>}
                      </div>
                      <h3 className="mt-3 truncate font-bold" title={run.title}>{run.title || "YouTube live"}</h3>
                      <div className={cn("mt-3 rounded-lg border p-3", run.status === "failed" ? "border-destructive/30 bg-destructive/5" : "border-primary/20 bg-primary/5")} aria-live="polite">
                        <p className="font-semibold">{statusLabel(run)}</p>
                        <p className="mt-1 text-xs leading-5 text-muted-foreground">{statusHint(run)}</p>
                        <div className="mt-3 grid grid-cols-3 gap-2 text-xs">
                          <div><p className="text-muted-foreground">수집</p><p className="mt-1 font-semibold">{durationLabel(run.captured_seconds)}</p></div>
                          <div><p className="text-muted-foreground">완료 청크</p><p className="mt-1 font-semibold">{run.chunk_count || 0}개</p></div>
                          <div><p className="text-muted-foreground">마지막 갱신</p><p className="mt-1 font-semibold">{updatedAtLabel(run.updated_at)}</p></div>
                        </div>
                      </div>
                    </div>
                    <pre
                      ref={(element) => {
                        if (element) transcriptRefs.current.set(run.id, element);
                        else transcriptRefs.current.delete(run.id);
                      }}
                      onScroll={(event) => {
                        const element = event.currentTarget;
                        const distanceFromBottom = element.scrollHeight - element.scrollTop - element.clientHeight;
                        transcriptScrollState.current.set(run.id, {
                          scrollTop: element.scrollTop,
                          followTail: distanceFromBottom <= 24
                        });
                      }}
                      className="h-[340px] overflow-auto whitespace-pre-wrap bg-slate-950 p-4 font-mono text-xs leading-6 text-slate-100"
                    >
                      {run.transcript || "첫 번째 청크를 기다리고 있습니다..."}
                    </pre>
                  </article>
                ))}
              </div>
            )}
          </CardContent>
        </Card>
      </div>

      <footer className="studio-card-shadow flex min-h-0 items-center justify-between rounded-none border-x-0 border-b-0 border-t border-border bg-card px-5">
        <div className="flex items-center gap-3 text-sm"><Radio className="h-4 w-4" /><span className="font-semibold">실시간 전사</span><span className="h-6 w-px bg-border" /><span className="text-muted-foreground">{activeCount ? `${activeCount}개 방송 처리 중` : "대기 중"}</span></div>
        <span className="text-xs text-muted-foreground">{service.projectRoot ? `출력: ${service.projectRoot}\\data\\knowledge` : "실시간 출력 경로를 확인하세요."}</span>
      </footer>
    </>
  );
}
