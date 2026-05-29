from __future__ import annotations

import json
import os
import shutil
import subprocess
import sys
import time
from dataclasses import dataclass, field
from pathlib import Path
from typing import Callable, Iterable, Optional

from app_info import APP_NAME


AUDIO_EXTENSIONS = {
    ".aac", ".aiff", ".alac", ".amr", ".ape", ".au", ".caf", ".dts",
    ".flac", ".m4a", ".m4b", ".mid", ".midi", ".mp3", ".oga", ".ogg",
    ".opus", ".ra", ".snd", ".tta", ".voc", ".wav", ".weba", ".wma",
    ".wv",
}

VIDEO_EXTENSIONS = {
    ".3g2", ".3gp", ".asf", ".avi", ".divx", ".dv", ".f4v", ".flv",
    ".m2ts", ".m4v", ".mkv", ".mov", ".mp4", ".mpeg", ".mpg", ".mts",
    ".mxf", ".ogv", ".rm", ".rmvb", ".ts", ".vob", ".webm", ".wmv",
}

SUPPORTED_EXTENSIONS = sorted(AUDIO_EXTENSIONS | VIDEO_EXTENSIONS)
OUTPUT_FORMATS = ("txt", "srt", "vtt", "json", "tsv")
MODEL_NAMES = ("tiny", "base", "small", "medium", "large", "large-v2", "large-v3")


ProgressCallback = Callable[[str], None]


@dataclass
class TranscriptionOptions:
    model_name: str = "small"
    language: str = "ko"
    task: str = "transcribe"
    output_formats: list[str] = field(default_factory=lambda: ["txt", "srt"])
    output_dir: Optional[Path] = None
    overwrite: bool = False
    device: str = "auto"
    temperature: float = 0.0
    condition_on_previous_text: bool = False


@dataclass
class TranscriptionResult:
    source: Path
    text: str
    segments: list[dict]
    output_files: list[Path]
    elapsed_seconds: float


def _prepend_path(directory: Path) -> None:
    directory = directory.resolve()
    path_value = os.environ.get("PATH", "")
    paths = [Path(item).resolve() for item in path_value.split(os.pathsep) if item]
    if directory not in paths:
        os.environ["PATH"] = str(directory) + os.pathsep + path_value


def _runtime_roots() -> list[Path]:
    roots = [Path(__file__).resolve().parent, Path(sys.executable).resolve().parent]
    bundle_root = getattr(sys, "_MEIPASS", None)
    if bundle_root:
        roots.append(Path(bundle_root))
    return roots


def _ffmpeg_executable_name() -> str:
    return "ffmpeg.exe" if sys.platform == "win32" else "ffmpeg"


def _find_bundled_ffmpeg() -> Optional[Path]:
    executable_name = _ffmpeg_executable_name()
    candidate_dirs: list[Path] = []

    for root in _runtime_roots():
        candidate_dirs.extend(
            [
                root,
                root / "bin",
                root / "ffmpeg",
                root / "vendor" / "ffmpeg",
                root / "vendor" / "ffmpeg" / "windows",
                root / "vendor" / "ffmpeg" / "macos",
            ]
        )

    for directory in candidate_dirs:
        candidate = directory / executable_name
        if candidate.exists():
            return candidate

    return None


def _app_cache_dir() -> Path:
    if sys.platform == "win32":
        base = Path(os.environ.get("LOCALAPPDATA") or Path.home() / "AppData" / "Local")
    elif sys.platform == "darwin":
        base = Path.home() / "Library" / "Application Support"
    else:
        base = Path(os.environ.get("XDG_DATA_HOME") or Path.home() / ".local" / "share")
    return base / APP_NAME


def ensure_ffmpeg_on_path() -> Optional[Path]:
    existing = shutil.which("ffmpeg")
    if existing:
        return Path(existing)

    bundled = _find_bundled_ffmpeg()
    if bundled:
        _prepend_path(bundled.parent)
        return bundled

    try:
        import imageio_ffmpeg

        source = Path(imageio_ffmpeg.get_ffmpeg_exe())
    except Exception:
        return None

    target_dir = _app_cache_dir() / "bin"
    target_dir.mkdir(parents=True, exist_ok=True)
    target = target_dir / _ffmpeg_executable_name()

    if not target.exists() or target.stat().st_size != source.stat().st_size:
        shutil.copy2(source, target)
        if sys.platform != "win32":
            target.chmod(target.stat().st_mode | 0o755)

    _prepend_path(target_dir)
    return target


def check_ffmpeg() -> tuple[bool, str]:
    ensure_ffmpeg_on_path()
    ffmpeg = shutil.which("ffmpeg")
    if not ffmpeg:
        return False, "ffmpeg executable was not found."

    try:
        result = subprocess.run(
            [ffmpeg, "-version"],
            capture_output=True,
            text=True,
            timeout=5,
            check=False,
        )
    except Exception as exc:  # pragma: no cover - defensive environment check
        return False, f"ffmpeg exists but could not be executed: {exc}"

    if result.returncode != 0:
        return False, result.stderr.strip() or "ffmpeg returned a non-zero exit code."

    first_line = (result.stdout or "").splitlines()[0] if result.stdout else "ffmpeg"
    return True, first_line


def is_supported_media(path: Path) -> bool:
    return path.suffix.lower() in SUPPORTED_EXTENSIONS


def discover_media_files(folder: Path, recursive: bool = True) -> list[Path]:
    iterator: Iterable[Path] = folder.rglob("*") if recursive else folder.iterdir()
    return sorted(path for path in iterator if path.is_file() and is_supported_media(path))


def supported_filetype_patterns() -> str:
    return " ".join(f"*{ext}" for ext in SUPPORTED_EXTENSIONS)


def _format_timestamp(seconds: float, separator: str = ",") -> str:
    milliseconds = int(round(seconds * 1000.0))
    hours, remainder = divmod(milliseconds, 3_600_000)
    minutes, remainder = divmod(remainder, 60_000)
    secs, millis = divmod(remainder, 1000)
    return f"{hours:02d}:{minutes:02d}:{secs:02d}{separator}{millis:03d}"


def _output_path(source: Path, options: TranscriptionOptions, suffix: str) -> Path:
    output_dir = options.output_dir or source.parent
    output_dir.mkdir(parents=True, exist_ok=True)
    candidate = output_dir / f"{source.stem}.{suffix}"

    if options.overwrite or not candidate.exists():
        return candidate

    index = 1
    while True:
        next_candidate = output_dir / f"{source.stem}_{index}.{suffix}"
        if not next_candidate.exists():
            return next_candidate
        index += 1


def _write_txt(path: Path, source: Path, result: dict, elapsed: float, model_name: str) -> None:
    text = (result.get("text") or "").strip()
    segments = result.get("segments") or []

    with path.open("w", encoding="utf-8", newline="\n") as handle:
        handle.write("# Whisper transcription result\n")
        handle.write(f"# Source file: {source}\n")
        handle.write(f"# Model: {model_name}\n")
        handle.write(f"# Created: {time.strftime('%Y-%m-%d %H:%M:%S')}\n")
        handle.write(f"# Elapsed seconds: {elapsed:.1f}\n")
        handle.write("#" + "=" * 60 + "\n\n")
        handle.write("## Full text\n\n")
        handle.write(text + "\n\n")
        handle.write("## Segments\n\n")

        for segment in segments:
            start = _format_timestamp(float(segment["start"]), ".")[:8]
            end = _format_timestamp(float(segment["end"]), ".")[:8]
            handle.write(f"[{start}-{end}] {segment.get('text', '').strip()}\n")


def _write_srt(path: Path, result: dict) -> None:
    with path.open("w", encoding="utf-8", newline="\n") as handle:
        for index, segment in enumerate(result.get("segments") or [], start=1):
            handle.write(f"{index}\n")
            handle.write(
                f"{_format_timestamp(float(segment['start']))} --> "
                f"{_format_timestamp(float(segment['end']))}\n"
            )
            handle.write(segment.get("text", "").strip() + "\n\n")


def _write_vtt(path: Path, result: dict) -> None:
    with path.open("w", encoding="utf-8", newline="\n") as handle:
        handle.write("WEBVTT\n\n")
        for segment in result.get("segments") or []:
            handle.write(
                f"{_format_timestamp(float(segment['start']), '.')} --> "
                f"{_format_timestamp(float(segment['end']), '.')}\n"
            )
            handle.write(segment.get("text", "").strip() + "\n\n")


def _write_json(path: Path, source: Path, result: dict, elapsed: float, model_name: str) -> None:
    payload = {
        "source": str(source),
        "model": model_name,
        "elapsed_seconds": elapsed,
        "text": result.get("text", ""),
        "segments": result.get("segments", []),
        "language": result.get("language"),
    }
    path.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")


def _write_tsv(path: Path, result: dict) -> None:
    with path.open("w", encoding="utf-8", newline="\n") as handle:
        handle.write("start\tend\ttext\n")
        for segment in result.get("segments") or []:
            text = segment.get("text", "").strip().replace("\t", " ")
            handle.write(f"{segment['start']:.3f}\t{segment['end']:.3f}\t{text}\n")


def write_outputs(
    source: Path,
    result: dict,
    options: TranscriptionOptions,
    elapsed: float,
) -> list[Path]:
    output_files: list[Path] = []
    requested = [fmt.lower() for fmt in options.output_formats if fmt.lower() in OUTPUT_FORMATS]

    for output_format in requested:
        path = _output_path(source, options, output_format)
        if output_format == "txt":
            _write_txt(path, source, result, elapsed, options.model_name)
        elif output_format == "srt":
            _write_srt(path, result)
        elif output_format == "vtt":
            _write_vtt(path, result)
        elif output_format == "json":
            _write_json(path, source, result, elapsed, options.model_name)
        elif output_format == "tsv":
            _write_tsv(path, result)
        output_files.append(path)

    return output_files


class WhisperBatchEngine:
    def __init__(self, progress: Optional[ProgressCallback] = None):
        self._progress = progress or (lambda message: None)
        self._model_name: Optional[str] = None
        self._device: Optional[str] = None
        self._model = None

    def _emit(self, message: str) -> None:
        self._progress(message)

    def load_model(self, model_name: str, device: str = "auto") -> None:
        normalized_device = None if device == "auto" else device
        if self._model is not None and self._model_name == model_name and self._device == device:
            return

        import whisper

        self._emit(f"Loading Whisper model: {model_name}")
        self._model = whisper.load_model(model_name, device=normalized_device)
        self._model_name = model_name
        self._device = device
        self._emit(f"Model ready: {model_name}")

    def transcribe_file(self, source: Path, options: TranscriptionOptions) -> TranscriptionResult:
        if not source.exists():
            raise FileNotFoundError(source)

        ensure_ffmpeg_on_path()

        if not is_supported_media(source):
            self._emit(f"Warning: unknown extension, trying ffmpeg anyway: {source.name}")

        self.load_model(options.model_name, options.device)
        assert self._model is not None

        language = options.language.strip() or None
        fp16 = str(getattr(self._model, "device", "")).startswith("cuda")
        self._emit(f"Transcribing: {source.name}")
        started = time.time()
        raw_result = self._model.transcribe(
            str(source),
            language=language,
            task=options.task,
            fp16=fp16,
            verbose=False,
            temperature=options.temperature,
            condition_on_previous_text=options.condition_on_previous_text,
            no_speech_threshold=0.6,
            logprob_threshold=-1.0,
            compression_ratio_threshold=2.4,
        )
        elapsed = time.time() - started
        output_files = write_outputs(source, raw_result, options, elapsed)
        self._emit(f"Finished: {source.name} ({elapsed:.1f}s)")

        return TranscriptionResult(
            source=source,
            text=raw_result.get("text", ""),
            segments=raw_result.get("segments", []),
            output_files=output_files,
            elapsed_seconds=elapsed,
        )
