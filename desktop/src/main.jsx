import React, { useEffect, useMemo, useState } from "react";
import { createRoot } from "react-dom/client";
import {
  CheckCircle2,
  CircleHelp,
  FileAudio,
  FileVideo,
  FolderOpen,
  ListX,
  Loader2,
  Play,
  Plus,
  Settings,
  Square,
  Trash2,
  X
} from "lucide-react";
import "./styles.css";

const api = window.whisperDesktop;
const defaultFormats = { txt: true, srt: true, vtt: false, json: false, tsv: false };

function extensionOf(filePath) {
  const name = filePath.split(/[\\/]/).pop() ?? filePath;
  const ext = name.includes(".") ? name.split(".").pop() : "";
  return ext.toUpperCase() || "MEDIA";
}

function filenameOf(filePath) {
  return filePath.split(/[\\/]/).pop() ?? filePath;
}

function isVideo(filePath) {
  return ["MP4", "MOV", "MKV", "WEBM", "AVI", "WMV", "M4V", "FLV", "MPEG", "MPG", "M2TS", "MTS", "TS"].includes(extensionOf(filePath));
}

function humanSize(file) {
  if (file.sizeMb || file.sizeMb === 0) return `${file.sizeMb} MB`;
  return "-";
}

function formatLogTime(date = new Date()) {
  return [
    String(date.getHours()).padStart(2, "0"),
    String(date.getMinutes()).padStart(2, "0"),
    String(date.getSeconds()).padStart(2, "0")
  ].join(":");
}

function statusLabel(status) {
  if (status === "running") return "진행 중";
  if (status === "done") return "완료";
  if (status === "failed") return "실패";
  return "대기";
}

function App() {
  const [files, setFiles] = useState([]);
  const [ffmpeg, setFfmpeg] = useState({ state: "checking", detail: "확인 중" });
  const [logs, setLogs] = useState([]);
  const [running, setRunning] = useState(false);
  const [currentFile, setCurrentFile] = useState("");
  const [progress, setProgress] = useState({ value: 0, total: 0 });
  const [options, setOptions] = useState({
    model_name: "small",
    language: "ko",
    task: "transcribe",
    device: "auto",
    outputLocation: "source",
    output_dir: "",
    output_formats: defaultFormats,
    condition_on_previous_text: true,
    overwrite: false,
    recursive: true
  });

  const totalSize = useMemo(() => {
    return files.reduce((sum, file) => sum + (Number(file.sizeMb) || 0), 0);
  }, [files]);

  useEffect(() => {
    api.selfTest()
      .then((result) => {
        setFfmpeg({ state: result.ok ? "ok" : "missing", detail: result.detail });
        addLog(result.ok ? `ffmpeg 확인 완료 (${result.detail})` : `ffmpeg 확인 실패: ${result.detail}`, result.ok ? "success" : "error");
      })
      .catch((error) => {
        setFfmpeg({ state: "missing", detail: error.message });
        addLog(`ffmpeg 확인 실패: ${error.message}`, "error");
      });

    return api.onTranscriptionEvent((message) => {
      if (message.type === "log") {
        addLog(message.payload);
      } else if (message.type === "status") {
        setCurrentFile(message.payload.file);
        addLog(`${message.payload.file} 전사 시작`);
      } else if (message.type === "progress") {
        setProgress({ value: message.payload.value, total: message.payload.total });
      } else if (message.type === "file-state") {
        setFiles((previous) => previous.map((file, index) => (
          index === message.payload.index ? { ...file, status: message.payload.state } : file
        )));
      }
    });
  }, []);

  function addLog(message, level = "info") {
    const time = formatLogTime();
    setLogs((previous) => [...previous.slice(-199), { time, message, level }]);
  }

  function appendFiles(items) {
    setFiles((previous) => {
      const seen = new Set(previous.map((file) => file.path));
      const next = [...previous];
      for (const item of items) {
        const filePath = typeof item === "string" ? item : item.path;
        if (!filePath) continue;
        if (seen.has(filePath)) continue;
        next.push({
          path: filePath,
          name: typeof item === "string" ? filenameOf(filePath) : item.name,
          format: typeof item === "string" ? extensionOf(filePath) : item.format,
          sizeMb: typeof item === "string" ? "" : item.sizeMb,
          status: "waiting"
        });
        seen.add(filePath);
      }
      return next;
    });
  }

  async function addFiles() {
    const paths = await api.addFiles();
    appendFiles(paths);
    if (paths.length) addLog(`${paths.length}개 파일 추가`);
  }

  async function addFolder() {
    const paths = await api.addFolder(options.recursive);
    appendFiles(paths);
    addLog(`${paths.length}개 미디어 파일을 폴더에서 추가`);
  }

  function removeFile(index) {
    setFiles((previous) => previous.filter((_file, fileIndex) => fileIndex !== index));
  }

  async function chooseOutputFolder() {
    const folder = await api.selectOutputFolder();
    if (folder) {
      setOptions((previous) => ({ ...previous, outputLocation: "custom", output_dir: folder }));
    }
  }

  function selectedFormats() {
    return Object.entries(options.output_formats)
      .filter(([, enabled]) => enabled)
      .map(([format]) => format);
  }

  async function startTranscription() {
    if (!files.length) {
      addLog("전사할 파일을 먼저 추가하세요.", "warn");
      return;
    }

    const outputFormats = selectedFormats();
    if (!outputFormats.length) {
      addLog("출력 형식을 하나 이상 선택하세요.", "warn");
      return;
    }

    setRunning(true);
    setCurrentFile("");
    setProgress({ value: 0, total: files.length });
    setFiles((previous) => previous.map((file) => ({ ...file, status: "waiting" })));
    addLog("배치 전사를 시작합니다.");

    try {
      await api.startTranscription({
        files: files.map((file) => file.path),
        options: {
          model_name: options.model_name,
          language: options.language,
          task: options.task,
          device: options.device,
          output_formats: outputFormats,
          output_dir: options.outputLocation === "custom" ? options.output_dir : null,
          condition_on_previous_text: options.condition_on_previous_text,
          overwrite: options.overwrite
        }
      });
      addLog("모든 작업이 완료되었습니다.", "success");
    } catch (error) {
      addLog(`전사 실패: ${error.message}`, "error");
    } finally {
      setRunning(false);
    }
  }

  async function cancelTranscription() {
    await api.cancelTranscription();
    setRunning(false);
    addLog("현재 작업을 취소했습니다.", "warn");
  }

  function openOutputFolder() {
    const target = options.outputLocation === "custom" && options.output_dir
      ? options.output_dir
      : files[0]?.path?.replace(/[\\/][^\\/]+$/, "");
    if (target) api.openPath(target);
  }

  const percent = progress.total ? Math.round((progress.value / progress.total) * 100) : 0;

  return (
    <main className="app-shell">
      <header className="topbar">
        <section>
          <h1>Whisper Batch Transcriber</h1>
          <p>로컬에서 음성 · 영상 파일을 텍스트와 자막으로 변환합니다.</p>
        </section>
        <nav className="top-actions">
          <span className={`badge ${ffmpeg.state === "ok" ? "success" : ffmpeg.state === "missing" ? "danger" : ""}`}>
            {ffmpeg.state === "checking" ? <Loader2 size={18} className="spin" /> : <CheckCircle2 size={18} />}
            {ffmpeg.state === "ok" ? "ffmpeg 정상" : ffmpeg.state === "missing" ? "ffmpeg 확인 필요" : "ffmpeg 확인 중"}
          </span>
          <span className="badge blue">로컬 처리</span>
          <button className="ghost"><Settings size={20} /> 설정</button>
          <button className="ghost"><CircleHelp size={20} /> 도움말</button>
        </nav>
      </header>

      <div className="content-grid">
        <section className="left-column">
          <article className="card file-card">
            <div className="card-title">파일 목록 ({files.length})</div>
            <div className="toolbar">
              <button className="primary" onClick={addFiles}><Plus size={18} /> 파일 추가</button>
              <button onClick={addFolder}><Plus size={18} /> 폴더 추가</button>
              <button onClick={() => setFiles([])}><Trash2 size={18} /> 목록 비우기</button>
              <label className="inline-check push-right">
                <input
                  type="checkbox"
                  checked={options.recursive}
                  onChange={(event) => setOptions({ ...options, recursive: event.target.checked })}
                />
                하위 폴더까지 포함
              </label>
            </div>

            <div className="file-table">
              <div className="file-row head">
                <span>파일명</span>
                <span>형식</span>
                <span>크기</span>
                <span>상태</span>
                <span />
              </div>
              <div className="file-body">
                {files.length === 0 ? (
                  <div className="empty-state">파일 또는 폴더를 추가하세요.</div>
                ) : files.map((file, index) => (
                  <div className="file-row" key={file.path}>
                    <span className="file-name">
                      {isVideo(file.path) ? <FileVideo size={24} /> : <FileAudio size={24} />}
                      {file.name}
                    </span>
                    <span>{file.format}</span>
                    <span>{humanSize(file)}</span>
                    <span><span className={`state ${file.status}`}>{statusLabel(file.status)}</span></span>
                    <button className="icon-button" onClick={() => removeFile(index)}><X size={18} /></button>
                  </div>
                ))}
              </div>
              <footer>{files.length}개 파일 · 총 {Math.round(totalSize)} MB</footer>
            </div>
          </article>

          <article className="card progress-card">
            <div className="card-title">진행 상황</div>
            <div className="progress-meta">
              <span>현재 파일: {currentFile || "-"}</span>
              <span>전체 진행률: {progress.value} / {progress.total || files.length} ({percent}%)</span>
            </div>
            <div className="progress-track"><div style={{ width: `${percent}%` }}>{percent ? `${percent}%` : ""}</div></div>
            <div className="progress-footer">
              <span>{running ? "전사 중입니다. 잠시만 기다려 주세요." : "대기 중입니다."}</span>
              <button disabled={!running} onClick={cancelTranscription}><Square size={14} /> 현재 작업 취소</button>
            </div>
          </article>

          <article className="card log-card">
            <div className="card-heading">
              <div className="card-title">로그</div>
              <button onClick={() => setLogs([])}>로그 지우기</button>
            </div>
            <div className="log-list">
              {logs.length === 0 ? (
                <div className="empty-log">아직 로그가 없습니다.</div>
              ) : logs.map((log, index) => (
                <div className={`log-line ${log.level}`} key={`${log.time}-${index}`}>
                  <span>{log.time}</span>
                  <span>{log.message}</span>
                </div>
              ))}
            </div>
          </article>
        </section>

        <section className="right-column">
          <article className="card settings-card">
            <div className="card-title">전사 설정</div>
            <div className="form-grid">
              <label>
                모델
                <select value={options.model_name} onChange={(event) => setOptions({ ...options, model_name: event.target.value })}>
                  {["tiny", "base", "small", "medium", "large", "large-v2", "large-v3"].map((model) => (
                    <option key={model} value={model}>{model === "small" ? "small (추천)" : model}</option>
                  ))}
                </select>
              </label>
              <label>
                언어
                <div className="input-with-button">
                  <input value={options.language} onChange={(event) => setOptions({ ...options, language: event.target.value })} placeholder="ko" />
                  <button onClick={() => setOptions({ ...options, language: "" })}>×</button>
                </div>
              </label>
              <fieldset>
                <legend>작업</legend>
                <label className="radio"><input type="radio" checked={options.task === "transcribe"} onChange={() => setOptions({ ...options, task: "transcribe" })} /> 전사 (transcribe)</label>
                <label className="radio"><input type="radio" checked={options.task === "translate"} onChange={() => setOptions({ ...options, task: "translate" })} /> 번역 (translate)</label>
              </fieldset>
              <label>
                장치
                <select value={options.device} onChange={(event) => setOptions({ ...options, device: event.target.value })}>
                  {["auto", "cpu", "cuda", "mps"].map((device) => <option key={device}>{device}</option>)}
                </select>
              </label>
            </div>

            <div className="divider" />

            <div className="form-grid">
              <fieldset>
                <legend>출력 형식</legend>
                <div className="check-grid">
                  {Object.keys(defaultFormats).map((format) => (
                    <label key={format}>
                      <input
                        type="checkbox"
                        checked={options.output_formats[format]}
                        onChange={(event) => setOptions({
                          ...options,
                          output_formats: { ...options.output_formats, [format]: event.target.checked }
                        })}
                      />
                      {format.toUpperCase()}
                    </label>
                  ))}
                </div>
              </fieldset>
              <fieldset>
                <legend>출력 위치</legend>
                <label className="radio"><input type="radio" checked={options.outputLocation === "source"} onChange={() => setOptions({ ...options, outputLocation: "source" })} /> 원본 파일 옆에 저장</label>
                <label className="radio"><input type="radio" checked={options.outputLocation === "custom"} onChange={() => setOptions({ ...options, outputLocation: "custom" })} /> 다른 폴더에 저장</label>
                <div className="path-row">
                  <input value={options.output_dir} readOnly placeholder="C:\\Users\\User\\Documents\\Transcripts" />
                  <button onClick={chooseOutputFolder}>변경</button>
                </div>
              </fieldset>
            </div>

            <div className="divider" />

            <details open>
              <summary>고급 설정</summary>
              <label className="inline-check">
                <input
                  type="checkbox"
                  checked={options.condition_on_previous_text}
                  onChange={(event) => setOptions({ ...options, condition_on_previous_text: event.target.checked })}
                />
                이전 문맥 사용 (권장)
              </label>
              <label className="inline-check">
                <input
                  type="checkbox"
                  checked={options.overwrite}
                  onChange={(event) => setOptions({ ...options, overwrite: event.target.checked })}
                />
                기존 파일 덮어쓰기
              </label>
            </details>
          </article>

          <button className="start-button" disabled={running} onClick={startTranscription}>
            <Play size={28} fill="currentColor" /> 전사 시작
          </button>
          <button className="open-output" onClick={openOutputFolder}>
            <FolderOpen size={28} /> 출력 폴더 열기
          </button>
        </section>
      </div>
    </main>
  );
}

createRoot(document.getElementById("root")).render(<App />);
