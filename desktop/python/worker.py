from __future__ import annotations

import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from transcriber_core import (  # noqa: E402
    TranscriptionOptions,
    WhisperBatchEngine,
    check_ffmpeg,
    discover_media_files,
)


def emit(message_type: str, payload=None) -> None:
    print(json.dumps({"type": message_type, "payload": payload}, ensure_ascii=False), flush=True)


def read_payload() -> dict:
    raw = sys.stdin.read().strip()
    if not raw:
        return {}
    return json.loads(raw)


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


def command_transcribe() -> None:
    payload = read_payload()
    files = [Path(item) for item in payload.get("files", [])]
    options_payload = payload.get("options", {})
    output_dir = options_payload.get("output_dir")
    options = TranscriptionOptions(
        model_name=options_payload.get("model_name", "small"),
        language=options_payload.get("language", "ko"),
        task=options_payload.get("task", "transcribe"),
        output_formats=options_payload.get("output_formats", ["txt", "srt"]),
        output_dir=Path(output_dir) if output_dir else None,
        overwrite=bool(options_payload.get("overwrite", False)),
        device=options_payload.get("device", "auto"),
        condition_on_previous_text=bool(options_payload.get("condition_on_previous_text", False)),
    )

    output_files: list[str] = []
    engine = WhisperBatchEngine(progress=lambda message: emit("log", message))
    total = len(files)
    for index, path in enumerate(files, start=1):
        emit("file-state", {"index": index - 1, "state": "running"})
        emit("status", {"index": index, "total": total, "file": path.name})
        result = engine.transcribe_file(path, options)
        output_files.extend(str(item) for item in result.output_files)
        emit("file-state", {"index": index - 1, "state": "done"})
        emit("progress", {"value": index, "total": total})

    emit("done", {"output_files": output_files})


def main() -> None:
    if len(sys.argv) < 2:
        raise SystemExit("Missing command")

    command = sys.argv[1]
    if command == "self-test":
        command_self_test()
    elif command == "discover":
        command_discover()
    elif command == "transcribe":
        command_transcribe()
    else:
        raise SystemExit(f"Unknown command: {command}")


if __name__ == "__main__":
    main()
