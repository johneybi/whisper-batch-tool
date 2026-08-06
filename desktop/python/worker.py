from __future__ import annotations

import json
import sys
import traceback
from pathlib import Path

if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
if hasattr(sys.stderr, "reconfigure"):
    sys.stderr.reconfigure(encoding="utf-8", errors="replace")

ROOT = Path(__file__).resolve().parents[2]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from transcriber_core import (  # noqa: E402
    TranscriptionOptions,
    WhisperBatchEngine,
    check_ffmpeg,
    discover_media_files,
    get_torch_runtime_info,
    validate_transcription_options,
)


def emit(message_type: str, payload=None) -> None:
    print(json.dumps({"type": message_type, "payload": payload}, ensure_ascii=False), flush=True)


def read_payload() -> dict:
    raw = sys.stdin.buffer.read().decode("utf-8").strip()
    if not raw:
        return {}
    return json.loads(raw)


def user_error_message(exc: Exception) -> str:
    message = str(exc) or exc.__class__.__name__
    if isinstance(exc, FileNotFoundError):
        return f"File not found: {message}"
    if "Failed to load audio:" not in message:
        return message

    lines = [line.strip() for line in message.replace("\r", "\n").split("\n") if line.strip()]
    for prefix in ("Error opening input:", "Error opening input file", "Error opening input files:"):
        for line in reversed(lines):
            if line.startswith(prefix):
                return f"Failed to load audio: {line}"
    return "Failed to load audio. The file may be corrupt or unsupported by ffmpeg."

def command_self_test() -> None:
    ok, detail = check_ffmpeg()
    emit("done", {"ok": ok, "detail": detail})
    raise SystemExit(0 if ok else 1)


def command_discover() -> None:
    payload = read_payload()
    folder = Path(payload["folder"])
    recursive = bool(payload.get("recursive", True))
    files = discover_media_files(folder, recursive=recursive)
    emit(
        "done",
        [
            {
                "path": str(path),
                "name": path.name,
                "format": path.suffix.upper().lstrip(".") or "MEDIA",
                "sizeMb": round(path.stat().st_size / (1024 * 1024)),
            }
            for path in files
        ],
    )


def command_runtime_info() -> None:
    info = get_torch_runtime_info()
    emit(
        "done",
        {
            "installed": info.installed,
            "version": info.version,
            "cudaAvailable": info.cuda_available,
            "cudaVersion": info.cuda_version,
            "cudaDeviceName": info.cuda_device_name,
            "mpsAvailable": info.mps_available,
            "label": info.device_label(),
            "error": info.error,
        },
    )


def command_transcribe() -> None:
    payload = read_payload()
    files = [Path(item) for item in payload.get("files", [])]
    options_payload = payload.get("options", {})
    output_dir = options_payload.get("output_dir")
    try:
        options = validate_transcription_options(
            TranscriptionOptions(
                model_name=options_payload.get("model_name", "small"),
                language=options_payload.get("language", "ko"),
                task=options_payload.get("task", "transcribe"),
                output_formats=options_payload.get("output_formats", ["txt", "srt"]),
                output_dir=Path(output_dir) if output_dir else None,
                overwrite=options_payload.get("overwrite", False),
                device=options_payload.get("device", "auto"),
                condition_on_previous_text=options_payload.get("condition_on_previous_text", False),
            )
        )
    except ValueError as exc:
        message = f"Invalid transcription options: {exc}"
        emit("error", message)
        print(message, file=sys.stderr)
        raise SystemExit(2)

    output_files: list[str] = []
    successful_files: list[str] = []
    failed_files: list[dict] = []
    active_file = {"index": -1, "path": ""}

    def emit_frame_progress(current: int, total_frames: int) -> None:
        emit(
            "frame-progress",
            {
                "index": active_file["index"],
                "path": active_file["path"],
                "current": current,
                "total": total_frames,
                "batchTotal": total,
            },
        )

    engine = WhisperBatchEngine(
        progress=lambda message: emit("log", message),
        frame_progress=emit_frame_progress,
    )
    total = len(files)
    for index, path in enumerate(files, start=1):
        active_file["index"] = index - 1
        active_file["path"] = str(path)
        emit("file-state", {"index": index - 1, "path": str(path), "state": "running"})
        emit("status", {"index": index, "total": total, "file": path.name, "path": str(path)})
        try:
            result = engine.transcribe_file(path, options)
        except Exception as exc:
            error_message = user_error_message(exc)
            traceback.print_exc(file=sys.stderr)
            emit("file-state", {"index": index - 1, "path": str(path), "state": "failed", "error": error_message})
            emit("log", f"Failed: {path.name}: {error_message}")
            failed_files.append({"path": str(path), "error": error_message})
            emit("progress", {"value": index, "total": total})
            continue

        result_output_files = [str(item) for item in result.output_files]
        output_files.extend(result_output_files)
        successful_files.append(str(path))
        emit(
            "file-state",
            {
                "index": index - 1,
                "path": str(path),
                "state": "done",
                "outputFiles": result_output_files,
                "previewText": result.text[:8000],
                "elapsedSeconds": round(result.elapsed_seconds, 1),
            },
        )
        emit("progress", {"value": index, "total": total})

    emit(
        "done",
        {
            "output_files": output_files,
            "successful_files": successful_files,
            "failed_files": failed_files,
            "summary": {
                "total": total,
                "succeeded": len(successful_files),
                "failed": len(failed_files),
            },
        },
    )


def main() -> None:
    if len(sys.argv) < 2:
        raise SystemExit("Missing command")

    command = sys.argv[1]
    if command == "self-test":
        command_self_test()
    elif command == "runtime-info":
        command_runtime_info()
    elif command == "discover":
        command_discover()
    elif command == "transcribe":
        command_transcribe()
    else:
        raise SystemExit(f"Unknown command: {command}")


if __name__ == "__main__":
    main()
