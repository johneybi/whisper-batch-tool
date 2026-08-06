import React, { useEffect, useMemo, useRef, useState } from "react";
import { createRoot } from "react-dom/client";
import { AnimatePresence, motion, useReducedMotion } from "motion/react";
import {
  CheckCircle2,
  CircleHelp,
  ClipboardCopy,
  CloudUpload,
  FileAudio,
  FilePlus,
  FileText,
  FileVideo,
  FolderOpen,
  FolderPlus,
  Languages,
  Laptop,
  List,
  Loader2,
  Maximize2,
  Minus,
  PackageOpen,
  Play,
  Plus,
  Search,
  Settings,
  ShieldCheck,
  Square,
  Trash2,
  X,
  Zap
} from "lucide-react";

import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { Checkbox } from "@/components/ui/checkbox";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { Progress } from "@/components/ui/progress";
import { cn } from "@/lib/utils";
import "./styles.css";

const defaultFormats = { txt: true, srt: true, vtt: false, json: false, tsv: false };

const mockDesktopApi = {
  addFiles: async () => [],
  addFolder: async () => [],
  selectOutputFolder: async () => "",
  selfTest: async () => ({
    ok: false,
    detail: "Electron 앱에서 실행하면 ffmpeg 상태를 확인합니다."
  }),
  runtimeInfo: async () => ({ label: "Electron 앱에서 실행하면 장치 상태를 확인합니다." }),
  startTranscription: async () => ({ ok: true }),
  cancelTranscription: async () => undefined,
  cancelFileScan: async () => undefined,
  readTextFile: async () => "",
  openPath: async () => undefined,
  showItemInFolder: async () => undefined,
  getPathForFile: () => "",
  resolveDroppedPaths: async () => ({ files: [], skipped: 0 }),
  minimizeWindow: async () => undefined,
  toggleMaximizeWindow: async () => undefined,
  closeWindow: async () => undefined,
  onTranscriptionEvent: () => () => undefined
};

const api = window.whisperDesktop ?? mockDesktopApi;
const isElectronRuntime = Boolean(window.whisperDesktop);

const selectClassName =
  "flex h-10 w-full rounded-lg border border-input bg-background px-3 py-2 text-sm shadow-sm transition-colors focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring disabled:cursor-not-allowed disabled:opacity-50";

const presetItems = [
  {
    id: "fast",
    label: "Fast",
    description: "빠른 초안 생성",
    icon: Zap,
    options: { model_name: "base", task: "transcribe", condition_on_previous_text: false }
  },
  {
    id: "balanced",
    label: "Balanced",
    description: "추천 · 속도와 정확도 균형",
    icon: Settings,
    options: { model_name: "small", task: "transcribe", condition_on_previous_text: false }
  },
  {
    id: "accurate",
    label: "Accurate",
    description: "긴 파일과 회의록에 적합",
    icon: CheckCircle2,
    options: { model_name: "medium", task: "transcribe", condition_on_previous_text: false }
  },
  {
    id: "translate",
    label: "Translate to English",
    description: "Whisper 내장 영어 번역 전사",
    icon: Languages,
    options: { model_name: "small", task: "translate", condition_on_previous_text: false }
  }
];

const languageOptions = [
  { value: "", label: "Auto detect" },
  { value: "ko", label: "Korean (ko)" },
  { value: "en", label: "English (en)" },
  { value: "ja", label: "Japanese (ja)" },
  { value: "zh", label: "Chinese (zh)" },
  { value: "es", label: "Spanish (es)" },
  { value: "fr", label: "French (fr)" },
  { value: "de", label: "German (de)" },
  { value: "ru", label: "Russian (ru)" },
  { value: "vi", label: "Vietnamese (vi)" },
  { value: "th", label: "Thai (th)" },
  { value: "id", label: "Indonesian (id)" }
];

function LogoMark() {
  return (
    <div className="flex h-11 w-11 shrink-0 items-center justify-center rounded-lg bg-primary text-primary-foreground shadow-sm">
      <div className="flex h-6 items-center gap-0.5">
        {[12, 20, 28, 18, 24].map((height, index) => (
          <span
            className="w-0.5 rounded-full bg-current"
            key={`${height}-${index}`}
            style={{ height }}
          />
        ))}
      </div>
    </div>
  );
}

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
  if (status === "running") return "Transcribing";
  if (status === "done") return "Completed";
  if (status === "failed") return "Failed";
  if (status === "canceled") return "Canceled";
  return "Queued";
}

function statusBadgeVariant(status) {
  if (status === "done") return "success";
  if (status === "failed") return "destructive";
  if (status === "running") return "warning";
  if (status === "canceled") return "outline";
  return "secondary";
}

function App() {
  const reduceMotion = useReducedMotion();
  const [files, setFiles] = useState([]);
  const [selectedFilePath, setSelectedFilePath] = useState("");
  const [ffmpeg, setFfmpeg] = useState({ state: "checking", detail: "확인 중" });
  const [runtimeInfo, setRuntimeInfo] = useState({ label: "Checking device..." });
  const [logs, setLogs] = useState([]);
  const [running, setRunning] = useState(false);
  const [currentFile, setCurrentFile] = useState("");
  const [progress, setProgress] = useState({ value: 0, total: 0 });
  const [activePreset, setActivePreset] = useState("balanced");
  const [searchQuery, setSearchQuery] = useState("");
  const [dropActive, setDropActive] = useState(false);
  const [fileScan, setFileScan] = useState({ active: false, label: "" });
  const [logOpen, setLogOpen] = useState(false);
  const [helpOpen, setHelpOpen] = useState(false);
  const [commandOpen, setCommandOpen] = useState(false);
  const [advancedOpen, setAdvancedOpen] = useState(false);
  const [activeOutputPath, setActiveOutputPath] = useState("");
  const [previewContent, setPreviewContent] = useState("");
  const [previewLoading, setPreviewLoading] = useState(false);
  const dropDepth = useRef(0);
  const [options, setOptions] = useState({
    model_name: "small",
    language: "ko",
    task: "transcribe",
    device: "auto",
    outputLocation: "source",
    output_dir: "",
    output_formats: defaultFormats,
    condition_on_previous_text: false,
    overwrite: false,
    recursive: true
  });

  const totalSize = useMemo(() => {
    return files.reduce((sum, file) => sum + (Number(file.sizeMb) || 0), 0);
  }, [files]);

  const outputFormats = useMemo(() => {
    return Object.entries(options.output_formats)
      .filter(([, enabled]) => enabled)
      .map(([format]) => format.toUpperCase());
  }, [options.output_formats]);

  const selectedFile = useMemo(() => {
    return files.find((file) => file.path === selectedFilePath) ?? files[0] ?? null;
  }, [files, selectedFilePath]);

  const visibleFiles = useMemo(() => {
    const query = searchQuery.trim().toLowerCase();
    if (!query) return files;
    return files.filter((file) => file.name.toLowerCase().includes(query) || file.format.toLowerCase().includes(query));
  }, [files, searchQuery]);

  const percent = progress.total ? Math.round((progress.value / progress.total) * 100) : 0;
  const progressTotal = progress.total || files.length;
  const lastLog = logs[logs.length - 1];
  const queuedFiles = useMemo(() => files.filter((file) => file.status === "waiting"), [files]);
  const ctaLabel = queuedFiles.length
    ? `Start ${queuedFiles.length} queued file${queuedFiles.length === 1 ? "" : "s"}`
    : files.length
      ? "No queued files"
      : "Add files to start";
  const outputEntries = selectedFile?.outputFiles?.map((filePath) => ({
    path: filePath,
    label: extensionOf(filePath)
  })) ?? [];
  const previewText = previewContent || selectedFile?.previewText || "";
  const springTransition = reduceMotion
    ? { duration: 0 }
    : { type: "spring", stiffness: 420, damping: 34, mass: 0.7 };
  const easeTransition = reduceMotion
    ? { duration: 0 }
    : { duration: 0.18, ease: [0.22, 1, 0.36, 1] };
  const commands = [
    { label: "Add files", action: addFiles },
    { label: "Add folder", action: addFolder },
    { label: "Start transcription", action: startTranscription, disabled: !queuedFiles.length || running },
    { label: "Open output folder", action: openOutputFolder, disabled: !files.length && !options.output_dir },
    { label: "Clear completed", action: clearCompleted },
    { label: "Toggle overwrite", action: () => setOptions((previous) => ({ ...previous, overwrite: !previous.overwrite })) }
  ];

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

    api.runtimeInfo()
      .then((result) => {
        setRuntimeInfo(result);
        addLog(`Runtime: ${result.label}`);
      })
      .catch((error) => {
        setRuntimeInfo({ label: "Device status unavailable", error: error.message });
        addLog(`Runtime 확인 실패: ${error.message}`, "warn");
      });

    return api.onTranscriptionEvent((message) => {
      if (message.type === "log") {
        addLog(message.payload);
      } else if (message.type === "status") {
        setCurrentFile(message.payload.file);
        setSelectedFilePath(message.payload.path || message.payload.file);
        addLog(`${message.payload.file} 전사 시작`);
      } else if (message.type === "progress") {
        setProgress({ value: message.payload.value, total: message.payload.total });
      } else if (message.type === "frame-progress") {
        const frameTotal = Math.max(Number(message.payload.total) || 1, 1);
        const frameCurrent = Math.max(0, Math.min(Number(message.payload.current) || 0, frameTotal));
        const framePercent = Math.round((frameCurrent / frameTotal) * 100);
        const fileIndex = Math.max(Number(message.payload.index) || 0, 0);
        setProgress({
          value: fileIndex + (frameCurrent / frameTotal),
          total: Math.max(Number(message.payload.batchTotal) || 0, fileIndex + 1)
        });
        setFiles((previous) => previous.map((file, index) => (
          (message.payload.path ? file.path === message.payload.path : index === message.payload.index)
            ? { ...file, status: "running", frameProgress: framePercent }
            : file
        )));
      } else if (message.type === "file-state") {
        if (message.payload.state === "failed") {
          setSelectedFilePath(message.payload.path || "");
          addLog(`${filenameOf(message.payload.path || "File")} 실패: ${message.payload.error || "Unknown error"}`, "error");
        }
        setFiles((previous) => previous.map((file, index) => (
          (message.payload.path ? file.path === message.payload.path : index === message.payload.index)
            ? {
                ...file,
                status: message.payload.state,
                frameProgress: message.payload.state === "done" ? 100 : message.payload.state === "running" ? 0 : file.frameProgress,
                outputFiles: message.payload.outputFiles ?? file.outputFiles,
                previewText: message.payload.previewText ?? file.previewText,
                elapsedSeconds: message.payload.elapsedSeconds ?? file.elapsedSeconds,
                error: message.payload.error ?? ""
              }
            : file
        )));
      }
    });
  }, []);

  useEffect(() => {
    const firstOutput = selectedFile?.outputFiles?.[0] ?? "";
    setActiveOutputPath((current) => {
      if (!firstOutput) return "";
      if (selectedFile?.outputFiles?.includes(current)) return current;
      return firstOutput;
    });
    if (!firstOutput) {
      setPreviewContent("");
    }
  }, [selectedFile?.path, selectedFile?.outputFiles]);

  useEffect(() => {
    let canceled = false;

    async function loadPreviewFile() {
      if (!activeOutputPath) {
        setPreviewContent("");
        return;
      }

      setPreviewLoading(true);
      try {
        const content = await api.readTextFile(activeOutputPath);
        if (!canceled) setPreviewContent(content);
      } catch (error) {
        if (!canceled) {
          setPreviewContent("");
          addLog(`Preview 읽기 실패: ${error.message}`, "warn");
        }
      } finally {
        if (!canceled) setPreviewLoading(false);
      }
    }

    loadPreviewFile();
    return () => {
      canceled = true;
    };
  }, [activeOutputPath]);

  useEffect(() => {
    function onKeyDown(event) {
      if ((event.ctrlKey || event.metaKey) && event.key.toLowerCase() === "k") {
        event.preventDefault();
        setCommandOpen((open) => !open);
      }
    }

    window.addEventListener("keydown", onKeyDown);
    return () => window.removeEventListener("keydown", onKeyDown);
  }, []);

  function addLog(message, level = "info") {
    const time = formatLogTime();
    setLogs((previous) => [...previous.slice(-199), { time, message, level }]);
  }

  function normalizeFileItem(item) {
    const filePath = typeof item === "string" ? item : item.path;
    if (!filePath) return null;

    return {
      path: filePath,
      name: typeof item === "string" ? filenameOf(filePath) : item.name,
      format: typeof item === "string" ? extensionOf(filePath) : item.format,
      sizeMb: typeof item === "string" ? "" : item.sizeMb,
      status: "waiting",
      frameProgress: 0
    };
  }

  function appendFiles(items) {
    const added = [];

    setFiles((previous) => {
      const seen = new Set(previous.map((file) => file.path));
      const next = [...previous];

      for (const item of items) {
        const file = normalizeFileItem(item);
        if (!file || seen.has(file.path)) continue;
        next.push(file);
        added.push(file);
        seen.add(file.path);
      }

      return next;
    });

    if (added[0] && !selectedFilePath) {
      setSelectedFilePath(added[0].path);
    }

    return added;
  }

  async function addFiles() {
    setFileScan({ active: true, label: "Selecting files..." });
    const selected = await api.addFiles();
    setFileScan({ active: false, label: "" });
    const added = appendFiles(selected);
    if (added.length) addLog(`${added.length}개 파일 추가`, "success");
  }

  async function addFolder() {
    setFileScan({ active: true, label: "Scanning folder..." });
    const selected = await api.addFolder(options.recursive);
    setFileScan({ active: false, label: "" });
    const added = appendFiles(selected);
    if (added.length) addLog(`${added.length}개 미디어 파일을 폴더에서 추가`, "success");
  }

  async function handleDrop(event) {
    event.preventDefault();
    dropDepth.current = 0;
    setDropActive(false);

    const droppedPaths = Array.from(event.dataTransfer.files)
      .map((file) => api.getPathForFile?.(file) || file.path)
      .filter(Boolean);

    if (!droppedPaths.length) {
      addLog(
        isElectronRuntime
          ? "드롭된 항목의 파일 경로를 읽지 못했습니다. Add files 또는 Add folder를 사용해 주세요."
          : "브라우저 미리보기에서는 OS 파일 경로를 받을 수 없습니다. Electron 앱에서 드래그하거나 Add files를 사용해 주세요.",
        "warn"
      );
      return;
    }

    let resolved;
    setFileScan({ active: true, label: "Resolving dropped files..." });
    try {
      resolved = await api.resolveDroppedPaths(droppedPaths, options.recursive);
    } catch (error) {
      addLog(`드롭한 파일을 읽지 못했습니다: ${error.message}`, "error");
      setFileScan({ active: false, label: "" });
      return;
    }

    setFileScan({ active: false, label: "" });
    const resolvedFiles = resolved.files ?? [];
    const skipped = resolved.skipped ?? 0;

    if (!resolvedFiles.length) {
      addLog(`추가할 수 있는 미디어 파일이 없습니다.${skipped ? ` ${skipped}개 항목을 제외했습니다.` : ""}`, "warn");
      return;
    }

    const added = appendFiles(resolvedFiles);
    addLog(`${added.length}개 파일 추가${skipped ? ` · ${skipped}개 항목 제외` : ""} · 중복 파일은 자동 제외`, added.length ? "success" : "warn");
  }

  async function cancelFileScan() {
    await api.cancelFileScan?.();
    setFileScan({ active: false, label: "" });
    addLog("File scan canceled.", "warn");
  }

  function handleDragEnter(event) {
    event.preventDefault();
    if (!Array.from(event.dataTransfer.types ?? []).includes("Files")) return;
    dropDepth.current += 1;
    setDropActive(true);
  }

  function handleDragOver(event) {
    event.preventDefault();
    if (event.dataTransfer) {
      event.dataTransfer.dropEffect = "copy";
    }
    setDropActive(true);
  }

  function handleDragLeave(event) {
    event.preventDefault();
    dropDepth.current = Math.max(0, dropDepth.current - 1);
    if (dropDepth.current === 0) {
      setDropActive(false);
    }
  }

  function removeFile(index) {
    setFiles((previous) => {
      const target = previous[index];
      const next = previous.filter((_file, fileIndex) => fileIndex !== index);
      if (target?.path === selectedFilePath) {
        setSelectedFilePath(next[0]?.path ?? "");
      }
      return next;
    });
  }

  function clearCompleted() {
    setFiles((previous) => {
      const next = previous.filter((file) => file.status !== "done");
      if (!next.some((file) => file.path === selectedFilePath)) {
        setSelectedFilePath(next[0]?.path ?? "");
      }
      return next;
    });
    addLog("완료된 파일을 큐에서 정리했습니다.");
  }

  function requeueSelectedFile() {
    if (!selectedFile) return;
    setFiles((previous) => previous.map((file) => (
      file.path === selectedFile.path
        ? { ...file, status: "waiting", frameProgress: 0, error: "", outputFiles: undefined, previewText: "", elapsedSeconds: undefined }
        : file
    )));
    setActiveOutputPath("");
    setPreviewContent("");
    addLog(`${selectedFile.name} 파일을 다시 대기 상태로 돌렸습니다.`);
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

  function applyPreset(preset) {
    setActivePreset(preset.id);
    setOptions((previous) => ({ ...previous, ...preset.options }));
    addLog(`${preset.label} 프리셋 적용`);
  }

  async function copyPreviewText() {
    const text = previewText.trim();
    if (!text) {
      addLog("복사할 전사 결과가 아직 없습니다.", "warn");
      return;
    }

    await navigator.clipboard.writeText(text);
    addLog(`${selectedFile.name} 전사 결과를 클립보드에 복사했습니다.`, "success");
  }

  async function startTranscription() {
    if (!files.length) {
      addLog("전사를 시작할 파일을 먼저 추가해 주세요.", "warn");
      return;
    }

    if (!queuedFiles.length) {
      addLog("대기 중인 파일이 없습니다. 실패 파일은 Retry later를 누르거나 새 파일을 추가해 주세요.", "warn");
      return;
    }

    const formats = selectedFormats();
    if (!formats.length) {
      addLog("출력 형식을 하나 이상 선택해 주세요.", "warn");
      return;
    }

    setRunning(true);
    setCurrentFile("");
    setProgress({ value: 0, total: queuedFiles.length });
    setActiveOutputPath("");
    setPreviewContent("");
    setFiles((previous) => previous.map((file) => (
      queuedFiles.some((queued) => queued.path === file.path)
        ? {
            ...file,
            status: "waiting",
            frameProgress: 0,
            outputFiles: undefined,
            previewText: "",
            elapsedSeconds: undefined,
            error: ""
          }
        : file
    )));
    addLog(`배치 전사 시작 · ${queuedFiles.length}개 대기 파일 · ${outputFormats.join(", ")}`);

    try {
      const result = await api.startTranscription({
        files: queuedFiles.map((file) => file.path),
        options: {
          model_name: options.model_name,
          language: options.language,
          task: options.task,
          device: options.device,
          output_formats: formats,
          output_dir: options.outputLocation === "custom" ? options.output_dir : null,
          condition_on_previous_text: options.condition_on_previous_text,
          overwrite: options.overwrite
        }
      });

      if (result?.canceled) {
        setFiles((previous) => previous.map((file) => (
          file.status === "running"
            ? { ...file, status: "canceled", error: "사용자가 배치 작업을 취소했습니다." }
            : file
        )));
        setCurrentFile("");
        addLog("배치 전사가 취소되었습니다.", "warn");
        return;
      }

      const failedFiles = result?.failed_files ?? [];
      const successfulFiles = result?.successful_files ?? [];
      if (failedFiles.length) {
        const firstFailure = failedFiles[0];
        const firstFailureName = filenameOf(firstFailure?.path || "File");
        const firstFailureMessage = firstFailure?.error || "Unknown error";
        addLog(`${failedFiles.length}개 파일 실패 · ${firstFailureName}: ${firstFailureMessage}`, successfulFiles.length ? "warn" : "error");
      } else {
        addLog("모든 작업이 완료되었습니다.", "success");
      }
    } catch (error) {
      addLog(`전사 실패: ${error.message}`, "error");
    } finally {
      setRunning(false);
    }
  }

  async function cancelTranscription() {
    await api.cancelTranscription();
    setRunning(false);
    setCurrentFile("");
    setFiles((previous) => previous.map((file) => (
      file.status === "running"
        ? { ...file, status: "canceled", error: "사용자가 배치 작업을 취소했습니다." }
        : file
    )));
    addLog("배치 작업을 취소했습니다. 아직 대기 중인 파일은 다시 시작할 수 있습니다.", "warn");
  }

  function openOutputFolder() {
    const target = options.outputLocation === "custom" && options.output_dir
      ? options.output_dir
      : selectedFile?.path?.replace(/[\\/][^\\/]+$/, "") ?? files[0]?.path?.replace(/[\\/][^\\/]+$/, "");
    if (target) api.openPath(target);
  }

  function openSelectedOutput() {
    const firstOutput = activeOutputPath || selectedFile?.outputFiles?.[0];
    if (firstOutput) {
      api.showItemInFolder?.(firstOutput) ?? api.openPath(firstOutput);
      return;
    }

    openOutputFolder();
  }

  return (
    <main className="grid h-screen min-h-[900px] min-w-[1360px] grid-rows-[96px_1fr_56px] overflow-hidden bg-background text-foreground">
      <header className="studio-titlebar relative grid grid-cols-[430px_1fr] grid-rows-[48px_48px] overflow-hidden border-b border-border/70 bg-card">
        <section className="row-span-2 flex min-w-0 items-center gap-4 px-6">
          <LogoMark />
          <div className="min-w-0">
            <h1 className="text-2xl font-extrabold tracking-normal">Whisper Studio</h1>
            <p className="mt-1 truncate text-sm text-muted-foreground">
              로컬 전사 · 자막 생성 · 기기 안에서 처리
            </p>
          </div>
        </section>

        <div className="col-start-2 flex h-12 items-center justify-end px-6">
          <div className="studio-no-drag flex items-center gap-2">
            <Button
              variant="ghost"
              size="icon"
              className="h-8 w-8 text-muted-foreground hover:bg-muted"
              aria-label="설정"
              title="Advanced settings 열기"
              onClick={() => setAdvancedOpen(true)}
            >
              <Settings className="h-4.5 w-4.5" />
            </Button>
            <Button
              variant="ghost"
              size="icon"
              className="h-8 w-8 text-muted-foreground hover:bg-muted"
              aria-label="도움말"
              onClick={() => setHelpOpen((open) => !open)}
            >
              <CircleHelp className="h-4.5 w-4.5" />
            </Button>
            <div className="mx-1 h-7 w-px bg-border" />
            <Button
              variant="ghost"
              size="icon"
              aria-label="최소화"
              title="Minimize"
              onClick={() => api.minimizeWindow()}
            >
              <Minus className="h-4 w-4" />
            </Button>
            <Button
              variant="ghost"
              size="icon"
              aria-label="최대화"
              title="Maximize"
              onClick={() => api.toggleMaximizeWindow()}
            >
              <Maximize2 className="h-4 w-4" />
            </Button>
            <Button
              className="hover:bg-destructive hover:text-destructive-foreground"
              variant="ghost"
              size="icon"
              aria-label="닫기"
              title="Close"
              onClick={() => api.closeWindow()}
            >
              <X className="h-4 w-4" />
            </Button>
          </div>
        </div>

        <div className="studio-no-drag col-start-2 row-start-2 flex h-12 items-end justify-end">
          <div className="studio-header-cutout h-12 w-16 shrink-0" />
          <div className="flex h-12 flex-1 items-center justify-start gap-2.5 bg-background pl-1 pr-6">
            <Badge
              className="h-8 gap-2 rounded-lg border-transparent bg-emerald-50 px-3.5 text-xs text-emerald-700 shadow-none"
              title={ffmpeg.detail}
            >
              {ffmpeg.state === "checking" ? <Loader2 className="h-3 w-3 animate-spin" /> : <span className="h-1.5 w-1.5 rounded-full bg-emerald-500" />}
              {ffmpeg.state === "ok" ? "ffmpeg ready" : ffmpeg.state === "missing" ? "ffmpeg check needed" : "checking ffmpeg"}
            </Badge>
            <Badge className="h-8 gap-2 rounded-lg bg-background px-3.5 text-xs shadow-none" variant="outline">
              <ShieldCheck className="h-3.5 w-3.5" /> Local only
            </Badge>
            <Badge
              className={cn(
                "h-8 gap-2 rounded-lg bg-background px-3.5 text-xs shadow-none",
                !runtimeInfo.cudaAvailable && !runtimeInfo.mpsAvailable && "border-amber-200 bg-amber-50 text-amber-800"
              )}
              variant="outline"
              title={runtimeInfo.label}
            >
              <Laptop className="h-3.5 w-3.5" /> {runtimeInfo.cudaAvailable ? "CUDA ready" : runtimeInfo.mpsAvailable ? "MPS ready" : "CPU / Auto"}
            </Badge>
          </div>
        </div>
      </header>

      <div className="grid min-h-0 grid-cols-[minmax(760px,1fr)_520px] gap-3 p-3">
        <section className="grid min-h-0 grid-rows-[1fr_104px] gap-3">
          <Card className="flex min-h-0 flex-1 flex-col">
            <CardHeader className="h-[108px] shrink-0 pb-4">
              <div className="flex items-start justify-between gap-4">
                <div>
                  <CardTitle>Queue</CardTitle>
                  <p className="mt-2 text-sm text-muted-foreground">{files.length} files · {Math.round(totalSize)} MB</p>
                  <p className="mt-1 text-xs text-muted-foreground">{outputFormats.join(", ") || "TXT, SRT"} 외 3개 형식 지원</p>
                </div>
                <div className="flex items-center gap-2">
                  <div className="relative w-56">
                    <Search className="pointer-events-none absolute left-3 top-2.5 h-4 w-4 text-muted-foreground" />
                    <Input
                      className="h-11 pl-9"
                      value={searchQuery}
                      onChange={(event) => setSearchQuery(event.target.value)}
                      placeholder="Search files..."
                    />
                  </div>
                  <Button className="h-11 px-5" disabled={fileScan.active} onClick={addFiles}><Plus className="h-4 w-4" /> Add files</Button>
                  <Button className="h-11 px-4" disabled={fileScan.active} variant="outline" onClick={addFolder}><Plus className="h-4 w-4" /> Add folder</Button>
                  {fileScan.active && (
                    <Button className="h-11 px-4" variant="outline" onClick={cancelFileScan}>
                      <Square className="h-3.5 w-3.5" /> Cancel scan
                    </Button>
                  )}
                  <Button className="h-11 px-4" variant="outline" onClick={clearCompleted}><Trash2 className="h-4 w-4 text-destructive" /> Clear completed</Button>
                </div>
              </div>
            </CardHeader>
            <CardContent className="grid min-h-0 flex-1 grid-rows-[286px_1fr] gap-5">
              <motion.div
                className={cn(
                  "studio-soft-panel relative grid min-h-0 place-items-center rounded-lg border border-dashed border-[#d7dfe9] px-6 text-center transition-all duration-150",
                  dropActive && "border-primary bg-blue-50/90 shadow-[inset_0_0_0_2px_rgba(23,105,245,0.16),0_18px_45px_rgba(23,105,245,0.12)]"
                )}
                animate={{
                  scale: dropActive ? 1.012 : 1,
                  y: dropActive ? -2 : 0
                }}
                transition={springTransition}
                whileHover={reduceMotion ? undefined : { y: -1 }}
                onDragEnter={handleDragEnter}
                onDragOver={handleDragOver}
                onDragLeave={handleDragLeave}
                onDrop={handleDrop}
              >
                <motion.div
                  className="space-y-4"
                  animate={{ scale: dropActive ? 1.015 : 1 }}
                  transition={springTransition}
                >
                  <motion.div
                    className={cn(
                      "mx-auto grid h-14 w-20 place-items-center rounded-full bg-primary/10 text-primary transition-colors",
                      dropActive && "bg-primary text-primary-foreground"
                    )}
                    animate={{ rotate: dropActive ? -3 : 0 }}
                    transition={springTransition}
                  >
                    <CloudUpload className="h-8 w-8" />
                  </motion.div>
                  <div>
                    <p className="text-base font-bold">
                      {fileScan.active ? fileScan.label : dropActive ? "Release to add files" : "Drop audio or video files here"}
                    </p>
                    <p className={cn("mt-2 text-sm text-muted-foreground", dropActive && "font-medium text-primary")}>
                      {dropActive
                        ? "파일이나 폴더를 놓으면 큐에 추가합니다."
                        : "MP3, WAV, M4A, MP4, MOV, MKV 지원 · 미지원/중복 파일은 자동 제외"}
                    </p>
                  </div>
                  {fileScan.active && (
                    <div className="inline-flex items-center gap-2 rounded-md border bg-background px-3 py-2 text-sm text-muted-foreground">
                      <Loader2 className="h-4 w-4 animate-spin" />
                      <span>{fileScan.label}</span>
                    </div>
                  )}
                  <Label className="inline-flex items-center gap-2 text-sm text-muted-foreground">
                    <Checkbox
                      checked={options.recursive}
                      onChange={(event) => setOptions({ ...options, recursive: event.target.checked })}
                    />
                    Include subfolders
                  </Label>
                </motion.div>
              </motion.div>

              <div className="flex min-h-0 flex-col overflow-hidden rounded-lg border border-border bg-card">
                <div className="grid h-11 shrink-0 grid-cols-[44px_minmax(240px,1fr)_110px_110px_110px_150px_42px] items-center border-b bg-[#fbfcfe] px-4 text-sm font-medium text-muted-foreground">
                  <span />
                  <span>File</span>
                  <span>Type</span>
                  <span>Language</span>
                  <span>Model</span>
                  <span>Status</span>
                  <span />
                </div>
                <div className="min-h-0 flex-1 overflow-auto">
                  {files.length === 0 ? (
                    <div className="grid h-full min-h-[260px] place-items-center text-center">
                      <div className="space-y-3">
                        <PackageOpen className="mx-auto h-14 w-14 text-muted-foreground/45" />
                        <div>
                          <p className="font-medium text-muted-foreground">파일을 추가하면 여기에 표시됩니다.</p>
                          <p className="mt-2 text-sm text-muted-foreground/70">음성 또는 영상 파일을 추가해 시작해 보세요.</p>
                        </div>
                      </div>
                    </div>
                  ) : visibleFiles.map((file, index) => {
                    const active = selectedFile?.path === file.path;
                    const fileIndex = files.findIndex((item) => item.path === file.path);
                    const rowPercent = file.status === "done" ? 100 : file.status === "running" ? file.frameProgress ?? 0 : 0;

                    return (
                      <div
                        className={cn(
                          "grid min-h-[68px] w-full grid-cols-[44px_minmax(240px,1fr)_110px_110px_110px_150px_42px] items-center border-b px-4 text-left text-sm transition-colors last:border-b-0 hover:bg-muted/45",
                          active && "bg-accent/70"
                        )}
                        key={file.path}
                        role="button"
                        tabIndex={0}
                        onClick={() => setSelectedFilePath(file.path)}
                        onKeyDown={(event) => {
                          if (event.key === "Enter" || event.key === " ") {
                            event.preventDefault();
                            setSelectedFilePath(file.path);
                          }
                        }}
                      >
                        <Checkbox checked={active} readOnly tabIndex={-1} aria-hidden="true" />
                        <span className="flex min-w-0 items-center gap-3 font-semibold">
                          {isVideo(file.path) ? <FileVideo className="h-5 w-5 shrink-0 text-primary" /> : <FileAudio className="h-5 w-5 shrink-0 text-primary" />}
                          <span className="min-w-0">
                            <span className="block truncate" title={file.name}>{file.name}</span>
                            <span className="block text-xs font-normal text-muted-foreground">{humanSize(file)} · {outputFormats.join(", ") || "No output"}</span>
                          </span>
                        </span>
                        <span className="text-muted-foreground">{file.format}</span>
                        <span className="text-muted-foreground">{options.language || "auto"}</span>
                        <span className="text-muted-foreground">{options.model_name}</span>
                        <span className="space-y-1">
                          <Badge variant={statusBadgeVariant(file.status)}>{statusLabel(file.status)}</Badge>
                          {file.status === "running" && <Progress value={rowPercent} className="h-1.5" />}
                        </span>
                        <span className="flex justify-end">
                          <Button
                            aria-label={`${file.name} 제거`}
                            size="icon"
                            variant="ghost"
                            onClick={(event) => {
                              event.stopPropagation();
                              removeFile(fileIndex >= 0 ? fileIndex : index);
                            }}
                          >
                            <X className="h-4 w-4" />
                          </Button>
                        </span>
                      </div>
                    );
                  })}
                </div>
              </div>
            </CardContent>
          </Card>

          <Card className="min-h-0">
            <CardContent className="grid h-full grid-cols-[1fr_auto] items-center gap-5 p-5">
              <div className="space-y-3">
                <div className="grid grid-cols-[120px_1fr_120px] items-center text-sm">
                  <span className="font-semibold">현재 작업</span>
                  <Progress value={percent} className="h-3" />
                  <span className="text-right text-muted-foreground">{percent}% complete</span>
                </div>
                <p className="text-sm text-muted-foreground">현재 파일: {currentFile || selectedFile?.name || "-"}</p>
              </div>
              <Button disabled={!running} variant="outline" onClick={cancelTranscription}>
                <Square className="h-3.5 w-3.5" /> Cancel batch
              </Button>
            </CardContent>
          </Card>
        </section>

        <aside className="grid min-h-0 grid-rows-[minmax(0,1fr)_240px] gap-3 overflow-hidden">
          <Card className="flex min-h-0 flex-col overflow-hidden">
            <CardHeader className="shrink-0 pb-3">
              <CardTitle>Transcription Setup</CardTitle>
            </CardHeader>
            <CardContent className="flex min-h-0 flex-1 flex-col gap-3 pr-5">
              <div className="min-h-0 flex-1 space-y-3 overflow-auto pr-1">
                <div className="space-y-2">
                <Label>Preset</Label>
                <div className="grid grid-cols-2 gap-3">
                  {presetItems.map((preset) => {
                    const Icon = preset.icon;
                    return (
                      <button
                        className={cn(
                           "flex min-h-[64px] items-center gap-3 rounded-lg border border-border bg-card p-3 text-left transition-colors hover:bg-muted/60",
                          activePreset === preset.id && "border-primary bg-accent text-accent-foreground ring-1 ring-primary/50"
                        )}
                        key={preset.id}
                        onClick={() => applyPreset(preset)}
                      >
                         <Icon className="h-5 w-5 shrink-0 text-primary" />
                         <span>
                           <span className="block text-sm font-bold">{preset.label}</span>
                           <span className="mt-0.5 block text-xs text-muted-foreground">{preset.description}</span>
                        </span>
                      </button>
                    );
                  })}
                </div>
              </div>

              <div className="grid grid-cols-[1fr_1fr] gap-4">
                <div className="space-y-2">
                  <Label>Model</Label>
                  <select
                    className={selectClassName}
                    value={options.model_name}
                    onChange={(event) => setOptions({ ...options, model_name: event.target.value })}
                  >
                    {["tiny", "base", "small", "medium", "large", "large-v2", "large-v3"].map((model) => (
                      <option key={model} value={model}>{model === "small" ? "small recommended" : model}</option>
                    ))}
                  </select>
                </div>
                <div className="space-y-2">
                  <Label>Language</Label>
                  <select
                    className={selectClassName}
                    value={options.language}
                    onChange={(event) => setOptions({ ...options, language: event.target.value })}
                  >
                    {languageOptions.map((language) => (
                      <option key={language.value || "auto"} value={language.value}>{language.label}</option>
                    ))}
                  </select>
                  <p className="text-xs text-muted-foreground">
                    {options.language ? `${options.language}로 고정합니다.` : "Whisper가 언어를 자동 감지합니다."}
                  </p>
                </div>
              </div>

              <fieldset className="space-y-3">
                <legend className="text-sm font-semibold">Output format</legend>
                <div className="grid grid-cols-5 gap-2">
                  {Object.keys(defaultFormats).map((format) => (
                    <Label
                      className={cn(
                         "flex h-8 items-center justify-center rounded-lg border border-border bg-card text-xs font-semibold",
                        options.output_formats[format] && "border-primary bg-accent text-accent-foreground ring-1 ring-primary/40"
                      )}
                      key={format}
                    >
                      <Checkbox
                        className="sr-only"
                        checked={options.output_formats[format]}
                        onChange={(event) => setOptions({
                          ...options,
                          output_formats: { ...options.output_formats, [format]: event.target.checked }
                        })}
                      />
                      {format.toUpperCase()}
                    </Label>
                  ))}
                </div>
              </fieldset>

              <fieldset className="space-y-2">
                <legend className="mb-2 text-sm font-semibold">Save to</legend>
                <Label className="flex items-center gap-2 font-normal">
                  <input
                    className="h-4 w-4 accent-primary"
                    type="radio"
                    checked={options.outputLocation === "source"}
                    onChange={() => setOptions({ ...options, outputLocation: "source" })}
                  />
                  Same as source
                </Label>
                <Label className="flex items-center gap-2 font-normal">
                  <input
                    className="h-4 w-4 accent-primary"
                    type="radio"
                    checked={options.outputLocation === "custom"}
                    onChange={() => setOptions({ ...options, outputLocation: "custom" })}
                  />
                  Custom folder
                </Label>
                <div className="grid grid-cols-[1fr_76px] gap-2 pt-1">
                  <Input value={options.output_dir} readOnly placeholder="C:\\Users\\User\\Documents\\Transcripts" />
                  <Button variant="outline" onClick={chooseOutputFolder}>Change</Button>
                </div>
              </fieldset>

              <details
                className="rounded-lg border border-border bg-card p-3"
                open={advancedOpen}
                onToggle={(event) => setAdvancedOpen(event.currentTarget.open)}
              >
                <summary className="cursor-pointer text-sm font-semibold">Advanced settings</summary>
                <div className="space-y-3 pt-3">
                  <div>
                    <Label className="flex items-center gap-2 font-normal">
                      <Checkbox
                        checked={options.condition_on_previous_text}
                        onChange={(event) => setOptions({ ...options, condition_on_previous_text: event.target.checked })}
                      />
                      Use previous text as context
                    </Label>
                    <p className="mt-1 pl-6 text-xs leading-5 text-muted-foreground">
                      긴 녹음에서 앞 문맥을 이어 보지만, 반복 문장이 생기면 끄는 편이 낫습니다.
                    </p>
                  </div>
                  <div>
                    <Label className="flex items-center gap-2 font-normal">
                      <Checkbox
                        checked={options.overwrite}
                        onChange={(event) => setOptions({ ...options, overwrite: event.target.checked })}
                      />
                      Overwrite existing transcripts
                    </Label>
                    <p className="mt-1 pl-6 text-xs leading-5 text-muted-foreground">
                      끄면 같은 이름의 결과 파일이 있을 때 _1, _2처럼 새 파일로 저장합니다.
                    </p>
                  </div>
                  <div className="space-y-2">
                    <Label>Device</Label>
                    <select
                      className={selectClassName}
                      value={options.device}
                      onChange={(event) => setOptions({ ...options, device: event.target.value })}
                    >
                      <option value="auto">auto - Whisper chooses available runtime</option>
                      <option value="cpu">cpu - safest fallback</option>
                      <option value="cuda">cuda - NVIDIA GPU</option>
                      <option value="mps">mps - Apple Silicon</option>
                    </select>
                  </div>
                  <p className="text-xs leading-5 text-muted-foreground">{runtimeInfo.label}</p>
                </div>
              </details>

                {options.task === "translate" && (
                  <div className="rounded-lg border border-blue-200 bg-blue-50 p-3 text-xs leading-5 text-blue-800">
                    이 모드는 Whisper의 `translate` 작업입니다. 입력 음성을 영어 텍스트/영어 자막으로 바로 전사하며, 한국어 자막을 일본어/중국어 등으로 바꾸는 범용 번역기는 아닙니다.
                  </div>
                )}
              </div>

              <div className="shrink-0 space-y-2">
                <Button className="h-12 w-full text-base font-bold" disabled={running || !queuedFiles.length} onClick={startTranscription}>
                  <Play className="h-5 w-5" fill="currentColor" /> {running ? "Transcribing..." : ctaLabel}
                </Button>
                <Button className="h-11 w-full" variant="outline" onClick={openOutputFolder}>
                  <FolderOpen className="h-5 w-5" /> Open output folder
                </Button>
              </div>
            </CardContent>
          </Card>

          <Card className="flex min-h-0 flex-col">
            <CardHeader className="shrink-0 pb-3">
              <div className="flex items-center justify-between">
                <CardTitle>Result Preview</CardTitle>
                <div className="flex gap-2">
                  <Button size="sm" variant="outline" onClick={copyPreviewText} disabled={!previewText}>
                    <ClipboardCopy className="h-4 w-4" /> Copy
                  </Button>
                  <Button size="sm" variant="outline" onClick={openSelectedOutput} disabled={!selectedFile}>
                    <FolderOpen className="h-4 w-4" /> Open
                  </Button>
                </div>
              </div>
            </CardHeader>
            <CardContent className="min-h-0 flex-1">
              <div className="flex h-full min-h-0 flex-col rounded-lg border border-border bg-card p-4 text-center">
                {previewText ? (
                  <div className="flex min-h-0 flex-1 flex-col text-left">
                    <div className="mb-3 flex items-center justify-between gap-3">
                      <p className="truncate text-sm font-semibold">{selectedFile.name}</p>
                      {outputEntries.length > 0 && (
                        <div className="flex shrink-0 gap-1">
                          {outputEntries.map((entry) => (
                            <button
                              className={cn(
                                "h-7 rounded-md border px-2 text-xs font-semibold text-muted-foreground hover:bg-muted",
                                activeOutputPath === entry.path && "border-primary bg-accent text-accent-foreground"
                              )}
                              key={entry.path}
                              onClick={() => setActiveOutputPath(entry.path)}
                            >
                              {entry.label}
                            </button>
                          ))}
                        </div>
                      )}
                    </div>
                    <div className="min-h-0 flex-1 overflow-auto">
                      {previewLoading ? (
                        <p className="text-sm text-muted-foreground">Preview loading...</p>
                      ) : (
                        <pre className="whitespace-pre-wrap font-sans text-sm leading-6 text-foreground">{previewText}</pre>
                      )}
                    </div>
                  </div>
                ) : selectedFile ? (
                  <div className="space-y-2">
                    <FileText className="mx-auto h-8 w-8 text-primary" />
                    <p className="max-w-[360px] truncate text-sm font-semibold">{selectedFile.name}</p>
                    <p className="text-sm text-muted-foreground">
                      {selectedFile.error || "전사가 완료되면 선택한 파일의 텍스트가 여기에 표시됩니다."}
                    </p>
                    <p className="text-xs text-muted-foreground">지원 형식: TXT, SRT, VTT, JSON, TSV</p>
                    {(selectedFile.status === "failed" || selectedFile.status === "canceled") && (
                      <Button className="mt-2" size="sm" variant="outline" onClick={requeueSelectedFile}>
                        Requeue file
                      </Button>
                    )}
                  </div>
                ) : (
                  <div className="space-y-2">
                    <FileText className="mx-auto h-8 w-8 text-foreground" />
                    <p className="text-sm text-muted-foreground">파일을 추가하면 전사 결과가 여기에 표시됩니다.</p>
                    <p className="text-xs text-muted-foreground">지원 형식: TXT, SRT, VTT, JSON, TSV</p>
                  </div>
                )}
              </div>
            </CardContent>
          </Card>
        </aside>
      </div>

      <footer className="studio-card-shadow flex min-h-0 items-center justify-between rounded-none border-x-0 border-b-0 border-t border-border bg-card px-5">
        <div className="flex min-w-0 items-center gap-4 text-sm">
          <span className="flex items-center gap-2 font-semibold"><Zap className="h-4 w-4" /> Activity</span>
          <span className="h-6 w-px bg-border" />
          <span className="font-mono text-muted-foreground">{lastLog?.time ?? formatLogTime()}</span>
          <span className="h-1.5 w-1.5 rounded-full bg-emerald-500" />
          <span className={cn("truncate", lastLog?.level === "error" ? "text-destructive" : "text-emerald-700")}>
            {lastLog?.message ?? "ffmpeg 확인 완료"}
          </span>
        </div>
        <Button variant="outline" onClick={() => setLogOpen((open) => !open)}>
          <List className="h-4 w-4" /> View log
        </Button>
      </footer>

      <AnimatePresence>
        {logOpen && (
          <motion.div
            className="fixed bottom-20 right-5 z-50 w-[560px] rounded-2xl border bg-popover p-4 shadow-xl"
            initial={{ opacity: 0, y: 12, scale: 0.98 }}
            animate={{ opacity: 1, y: 0, scale: 1 }}
            exit={{ opacity: 0, y: 8, scale: 0.98 }}
            transition={easeTransition}
          >
          <div className="mb-3 flex items-center justify-between">
            <h2 className="text-sm font-bold">Activity Log</h2>
            <Button size="icon" variant="ghost" onClick={() => setLogOpen(false)}><X className="h-4 w-4" /></Button>
          </div>
          <div className="max-h-72 overflow-auto border-t pt-3 font-mono text-xs">
            {logs.length === 0 ? (
              <p className="text-muted-foreground">로그가 없습니다.</p>
            ) : logs.map((log, index) => (
              <div className="grid grid-cols-[76px_1fr] gap-3 py-1" key={`${log.time}-${index}`}>
                <span className="text-primary">{log.time}</span>
                <span
                  className={cn(
                    "text-foreground",
                    log.level === "success" && "text-emerald-700",
                    log.level === "warn" && "text-amber-700",
                    log.level === "error" && "text-destructive"
                  )}
                >
                  {log.message}
                </span>
              </div>
            ))}
          </div>
          </motion.div>
        )}
      </AnimatePresence>

      <AnimatePresence>
        {helpOpen && (
          <motion.div
            className="fixed right-5 top-24 z-50 w-[440px] rounded-2xl border bg-popover p-4 shadow-xl"
            initial={{ opacity: 0, y: -8, scale: 0.98 }}
            animate={{ opacity: 1, y: 0, scale: 1 }}
            exit={{ opacity: 0, y: -6, scale: 0.98 }}
            transition={easeTransition}
          >
          <div className="mb-3 flex items-center justify-between">
            <h2 className="text-sm font-bold">기능 안내</h2>
            <Button size="icon" variant="ghost" onClick={() => setHelpOpen(false)}><X className="h-4 w-4" /></Button>
          </div>
          <div className="space-y-3 border-t pt-3 text-sm leading-6 text-muted-foreground">
            <p><strong className="text-foreground">Transcribe</strong>: 음성을 원어 그대로 텍스트/자막으로 만듭니다.</p>
            <p><strong className="text-foreground">Translate to English</strong>: Whisper 내장 기능으로 입력 음성을 영어 텍스트/영어 자막으로 번역 전사합니다. 다른 출력 언어 번역은 별도 번역 엔진이 필요합니다.</p>
            <p><strong className="text-foreground">Language</strong>: Auto detect를 선택하면 Whisper가 언어를 감지합니다. 한국어 고정은 Korean (ko)를 선택합니다.</p>
            <p><strong className="text-foreground">Output</strong>: 선택한 TXT/SRT/VTT/JSON/TSV 파일을 원본 옆 또는 지정 폴더에 저장합니다.</p>
            <p><strong className="text-foreground">Device</strong>: {runtimeInfo.label}</p>
          </div>
          </motion.div>
        )}
      </AnimatePresence>

      <AnimatePresence>
        {commandOpen && (
          <motion.div
            className="fixed inset-0 z-50 flex items-start justify-center bg-slate-950/20 pt-24"
            initial={{ opacity: 0 }}
            animate={{ opacity: 1 }}
            exit={{ opacity: 0 }}
            transition={easeTransition}
            onClick={() => setCommandOpen(false)}
          >
          <motion.div
            className="w-[520px] rounded-2xl border bg-popover p-3 shadow-xl"
            initial={{ opacity: 0, y: -12, scale: 0.98 }}
            animate={{ opacity: 1, y: 0, scale: 1 }}
            exit={{ opacity: 0, y: -8, scale: 0.98 }}
            transition={springTransition}
            onClick={(event) => event.stopPropagation()}
          >
            <div className="flex items-center gap-2 border-b px-2 pb-3">
              <Search className="h-4 w-4 text-muted-foreground" />
              <span className="text-sm font-semibold">Command palette</span>
            </div>
            <div className="mt-2 space-y-1">
              {commands.map((command) => (
                <button
                  className="flex w-full items-center justify-between rounded-lg px-3 py-2 text-left text-sm enabled:hover:bg-muted disabled:cursor-not-allowed disabled:opacity-45"
                  disabled={command.disabled}
                  key={command.label}
                  onClick={() => {
                    setCommandOpen(false);
                    command.action();
                  }}
                >
                  <span>{command.label}</span>
                  <span className="text-xs text-muted-foreground">{command.disabled ? "Unavailable" : "Enter"}</span>
                </button>
              ))}
            </div>
          </motion.div>
          </motion.div>
        )}
      </AnimatePresence>
    </main>
  );
}

createRoot(document.getElementById("root")).render(<App />);
