import React, { useCallback, useEffect, useLayoutEffect, useMemo, useRef, useState } from "react";
import { ArrowLeft, Check, Clock3, Copy, Loader2, Play, Radio, RefreshCw, Square, Wifi } from "lucide-react";

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

function timestampToSeconds(value) {
  const parts = String(value || "").split(":").map(Number);
  if (parts.length !== 3 || parts.some(Number.isNaN)) return 0;
  return (parts[0] * 3600) + (parts[1] * 60) + parts[2];
}

function transcriptTimeLabel(seconds) {
  const safe = Math.max(0, Math.floor(seconds || 0));
  const minutes = Math.floor(safe / 60);
  const remaining = safe % 60;
  return `${String(minutes).padStart(2, "0")}:${String(remaining).padStart(2, "0")}`;
}

function buildTranscriptBlocks(transcript) {
  const blocks = [];
  let current = null;
  let lastTimestampMinute = -1;

  String(transcript || "").split("\n").forEach((line, index) => {
    const matched = line.match(/^\[(\d{2}:\d{2}:\d{2})\s*-\s*(\d{2}:\d{2}:\d{2})\]\s*(.+)$/);
    if (!matched) return;
    const startSeconds = timestampToSeconds(matched[1]);
    const endSeconds = timestampToSeconds(matched[2]);
    const text = matched[3].trim();
    if (!text) return;
    const minute = Math.floor(startSeconds / 60);
    const needsNewBlock = !current || minute !== current.minute || (current.text.length + text.length > 140);
    if (needsNewBlock) {
      current = {
        id: `${startSeconds}-${index}`,
        startSeconds,
        endSeconds,
        minute,
        showTimestamp: minute !== lastTimestampMinute,
        text
      };
      blocks.push(current);
      lastTimestampMinute = minute;
      return;
    }
    current.text = `${current.text} ${text}`;
    current.endSeconds = endSeconds;
  });

  return blocks;
}
function copyTextForRun(run) {
  const body = buildTranscriptBlocks(run.transcript).map((block) => block.text).join("\n\n") || String(run.transcript || "").trim();
  return [run.title || "YouTube live", body].filter(Boolean).join("\n\n");
}

async function copyText(value) {
  if (navigator.clipboard?.writeText) {
    await navigator.clipboard.writeText(value);
    return;
  }
  const textarea = document.createElement("textarea");
  textarea.value = value;
  textarea.setAttribute("readonly", "");
  textarea.style.position = "fixed";
  textarea.style.opacity = "0";
  document.body.appendChild(textarea);
  textarea.select();
  const copied = document.execCommand("copy");
  textarea.remove();
  if (!copied) throw new Error("클립보드에 복사하지 못했습니다.");
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
  const [chunkSeconds, setChunkSeconds] = useState(10);
  const [startFromBeginning, setStartFromBeginning] = useState(true);
  const [submitting, setSubmitting] = useState(false);
  const [error, setError] = useState("");
  const transcriptRefs = useRef(new Map());
  const transcriptScrollState = useRef(new Map());
  const previousTranscriptByRun = useRef(new Map());
  const incomingHighlightTimer = useRef(null);
  const [recentBlockIds, setRecentBlockIds] = useState(new Set());
  const [selectedRunId, setSelectedRunId] = useState(null);
  const [copiedRunId, setCopiedRunId] = useState(null);
  const copyFeedbackTimer = useRef(null);

  const activeCount = useMemo(() => runs.filter((run) => ACTIVE_STATES.has(run.status)).length, [runs]);
  const selectedRun = useMemo(() => runs.find((run) => run.id === selectedRunId) || null, [runs, selectedRunId]);

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

  const markIncomingTranscriptBlocks = useCallback((nextRuns) => {
    const incomingIds = [];
    nextRuns.forEach((run) => {
      const previousTranscript = previousTranscriptByRun.current.get(run.id);
      const nextTranscript = String(run.transcript || "");
      if (previousTranscript && nextTranscript.length > previousTranscript.length) {
        buildTranscriptBlocks(nextTranscript).slice(-2).forEach((block) => incomingIds.push(block.id));
      }
      previousTranscriptByRun.current.set(run.id, nextTranscript);
    });
    if (incomingIds.length === 0) return;
    setRecentBlockIds(new Set(incomingIds));
    if (incomingHighlightTimer.current) window.clearTimeout(incomingHighlightTimer.current);
    incomingHighlightTimer.current = window.setTimeout(() => setRecentBlockIds(new Set()), 2400);
  }, []);
  const refreshRuns = useCallback(async () => {
    try {
      const nextRuns = await api.listLiveRuns();
      markIncomingTranscriptBlocks(nextRuns);
      captureTranscriptScroll();
      setRuns(nextRuns);
      setError("");
    } catch (refreshError) {
      setError(refreshError.message);
    }
  }, [api, captureTranscriptScroll, markIncomingTranscriptBlocks]);

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
      if (incomingHighlightTimer.current) window.clearTimeout(incomingHighlightTimer.current);
      if (copyFeedbackTimer.current) window.clearTimeout(copyFeedbackTimer.current);
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

  async function copyRun(run) {
    try {
      await copyText(copyTextForRun(run));
      setCopiedRunId(run.id);
      if (copyFeedbackTimer.current) window.clearTimeout(copyFeedbackTimer.current);
      copyFeedbackTimer.current = window.setTimeout(() => setCopiedRunId(null), 1800);
      onLog?.(`제목과 전사문을 복사했습니다: ${run.title || "YouTube live"}`, "success");
    } catch (copyError) {
      setError(copyError.message || "클립보드에 복사하지 못했습니다.");
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
                  <option value={10}>10초 · 빠른 갱신</option>
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
            {selectedRun ? (
              <div className="flex min-h-full flex-col gap-4">
                <div className="flex items-center justify-between gap-3">
                  <Button size="sm" variant="ghost" onClick={() => setSelectedRunId(null)}><ArrowLeft className="h-4 w-4" /> 목록</Button>
                  <Button size="sm" variant="outline" onClick={() => copyRun(selectedRun)} disabled={!selectedRun.transcript}>
                    {copiedRunId === selectedRun.id ? <Check className="h-4 w-4" /> : <Copy className="h-4 w-4" />}
                    {copiedRunId === selectedRun.id ? "복사됨" : "제목 + 내용 복사"}
                  </Button>
                </div>
                <div className="rounded-xl border bg-card p-5">
                  <div className="flex items-start justify-between gap-3">
                    <div>
                      <Badge variant={selectedRun.status === "failed" ? "destructive" : ACTIVE_STATES.has(selectedRun.status) ? "success" : "secondary"}>{ACTIVE_STATES.has(selectedRun.status) && <Loader2 className="h-3 w-3 animate-spin" />}{statusLabel(selectedRun)}</Badge>
                      <h2 className="mt-3 text-xl font-bold leading-8">{selectedRun.title || "YouTube live"}</h2>
                      <p className="mt-1 text-sm text-muted-foreground">{selectedRun.author || selectedRun.source_url}</p>
                    </div>
                    {!TERMINAL_STATES.has(selectedRun.status) && <Button size="sm" variant="outline" onClick={() => stopRun(selectedRun.id)}><Square className="h-3.5 w-3.5" /> 중지</Button>}
                  </div>
                  <div className="mt-4 grid grid-cols-3 gap-3 rounded-lg bg-muted/50 p-3 text-sm">
                    <div><p className="text-xs text-muted-foreground">수집</p><p className="mt-1 font-semibold">{durationLabel(selectedRun.captured_seconds)}</p></div>
                    <div><p className="text-xs text-muted-foreground">완료 청크</p><p className="mt-1 font-semibold">{selectedRun.chunk_count || 0}개</p></div>
                    <div><p className="text-xs text-muted-foreground">마지막 갱신</p><p className="mt-1 font-semibold">{updatedAtLabel(selectedRun.updated_at)}</p></div>
                  </div>
                </div>
                <div ref={(element) => { if (element) transcriptRefs.current.set(selectedRun.id, element); else transcriptRefs.current.delete(selectedRun.id); }} onScroll={(event) => { const element = event.currentTarget; const distanceFromBottom = element.scrollHeight - element.scrollTop - element.clientHeight; transcriptScrollState.current.set(selectedRun.id, { scrollTop: element.scrollTop, followTail: distanceFromBottom <= 24 }); }} className="min-h-[420px] flex-1 overflow-auto rounded-xl bg-slate-950 px-8 py-7 text-slate-100">
                  {buildTranscriptBlocks(selectedRun.transcript).length > 0 ? (
                    <div className="mx-auto max-w-3xl space-y-6">
                      {buildTranscriptBlocks(selectedRun.transcript).map((block) => (
                        <section key={block.id} className={cn("transition-colors duration-700", recentBlockIds.has(block.id) && "rounded-md bg-primary/15 px-3 py-2")}>
                          {block.showTimestamp && <time className="mb-2 block text-xs font-medium tracking-wide text-slate-500" title={`정확한 시작 시각 ${durationLabel(block.startSeconds)}`}>{transcriptTimeLabel(block.startSeconds)}</time>}
                          <p className="text-base leading-8 text-slate-100">{block.text}</p>
                        </section>
                      ))}
                    </div>
                  ) : <div className="grid h-full min-h-[360px] place-items-center text-center text-sm leading-6 text-slate-400"><div><Loader2 className="mx-auto mb-3 h-5 w-5 animate-spin" /><p className="font-medium text-slate-200">{statusLabel(selectedRun)}</p><p className="mt-1 max-w-sm">{statusHint(selectedRun)}</p></div></div>}
                </div>
              </div>
            ) : runs.length === 0 ? (
              <div className="grid h-full place-items-center rounded-lg border border-dashed text-center text-muted-foreground"><div><Radio className="mx-auto mb-3 h-9 w-9" /><p className="font-semibold text-foreground">진행 중인 방송이 없습니다.</p><p className="mt-2 text-sm">왼쪽에 YouTube URL을 입력해 시작하세요.</p></div></div>
            ) : (
              <div className="grid grid-cols-2 gap-3">
                {runs.map((run) => (
                  <article className="cursor-pointer overflow-hidden rounded-xl border bg-card transition-colors hover:border-primary/50 focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-primary" key={run.id} role="button" tabIndex={0} onClick={() => setSelectedRunId(run.id)} onKeyDown={(event) => { if (event.key === "Enter" || event.key === " ") setSelectedRunId(run.id); }}>
                    <div className="border-b p-4">
                      <div className="flex items-center justify-between gap-3">
                        <Badge variant={run.status === "failed" ? "destructive" : ACTIVE_STATES.has(run.status) ? "success" : "secondary"}>{ACTIVE_STATES.has(run.status) && <Loader2 className="h-3 w-3 animate-spin" />}{statusLabel(run)}</Badge>
                        {!TERMINAL_STATES.has(run.status) && <Button size="sm" variant="outline" onClick={(event) => { event.stopPropagation(); stopRun(run.id); }}><Square className="h-3.5 w-3.5" /> 중지</Button>}
                      </div>
                      <h3 className="mt-3 truncate font-bold" title={run.title}>{run.title || "YouTube live"}</h3>
                      <p className="mt-2 line-clamp-2 text-sm leading-6 text-muted-foreground">{run.transcript ? buildTranscriptBlocks(run.transcript).at(-1)?.text : statusHint(run)}</p>
                      <div className="mt-4 flex items-center justify-between text-xs text-muted-foreground"><span>{run.chunk_count || 0}개 청크 · {durationLabel(run.captured_seconds)}</span><span className="font-medium text-primary">열기</span></div>
                    </div>
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
