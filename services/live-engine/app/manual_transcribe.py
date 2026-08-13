from __future__ import annotations

import argparse
import json
import logging
import shutil
import signal
import subprocess
import sys
import tempfile
import time
import wave
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from threading import Event
from typing import Any, Callable
from urllib.parse import parse_qs, urlparse

from .config import settings
from .transcriber import (
    CaptureError,
    ContinuousCaptureSession,
    TranscriptSegment,
    format_segments,
    get_whisper_model,
    probe_youtube_live_state,
    require_binary,
    streamlink_payload_is_live,
    suppress_midstream_outro_hallucinations,
    transcribe_captured_audio,
)


logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s %(levelname)s %(message)s",
)
LOGGER = logging.getLogger(__name__)


@dataclass(frozen=True)
class StreamMetadata:
    video_id: str
    title: str
    author: str
    is_live: bool


ProgressCallback = Callable[
    [Path, list[TranscriptSegment], float, int],
    None,
]
StatusCallback = Callable[[str, str], None]


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Transcribe one YouTube live stream without Docker.",
    )
    parser.add_argument("url", nargs="?", help="YouTube live or video URL")
    parser.add_argument("--title", help="Override the output title")
    parser.add_argument(
        "--output-dir",
        type=Path,
        default=settings.knowledge_dir,
        help="Transcript output directory",
    )
    parser.add_argument(
        "--chunk-seconds",
        type=int,
        default=settings.rolling_chunk_seconds,
    )
    parser.add_argument(
        "--max-chunks",
        type=int,
        default=0,
        help="Stop after this many chunks; 0 means unlimited",
    )
    parser.add_argument(
        "--check",
        action="store_true",
        help="Check native dependencies and exit",
    )
    parser.add_argument(
        "--check-model",
        action="store_true",
        help="Check dependencies, load the configured model, and exit",
    )
    return parser


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    if args.check or args.check_model:
        return check_native_environment(load_model=args.check_model)
    if not args.url:
        raise SystemExit("A YouTube URL is required unless --check is used.")
    if args.chunk_seconds <= 0:
        raise SystemExit("--chunk-seconds must be positive.")

    stop_event = Event()
    install_signal_handlers(stop_event)
    try:
        transcript_path = transcribe_url(
            source_url=args.url,
            title_override=args.title,
            output_dir=args.output_dir,
            chunk_seconds=args.chunk_seconds,
            max_chunks=max(0, args.max_chunks),
            stop_event=stop_event,
        )
    except KeyboardInterrupt:
        stop_event.set()
        return 130
    except Exception as exc:
        LOGGER.error("native transcription failed: %s", exc)
        return 1

    print(f"TRANSCRIPT_PATH={transcript_path}")
    return 0


def check_native_environment(*, load_model: bool = False) -> int:
    failures: list[str] = []
    for binary in ("ffmpeg", "streamlink", "yt-dlp"):
        try:
            resolved = require_binary(binary)
            print(f"[ok] {binary}: {resolved}")
        except Exception as exc:
            failures.append(str(exc))

    try:
        import ctranslate2

        device_count = ctranslate2.get_cuda_device_count()
        print(
            f"[ok] ctranslate2={ctranslate2.__version__} "
            f"cuda_devices={device_count}"
        )
        if settings.whisper_device == "cuda" and device_count < 1:
            failures.append(
                "CTranslate2 cannot see an NVIDIA CUDA device"
            )
    except Exception as exc:
        failures.append(f"CTranslate2/CUDA check failed: {exc}")

    try:
        import faster_whisper

        print(
            "[ok] faster-whisper="
            f"{getattr(faster_whisper, '__version__', 'installed')}"
        )
    except Exception as exc:
        failures.append(f"faster-whisper import failed: {exc}")

    if failures:
        for failure in failures:
            print(f"[error] {failure}", file=sys.stderr)
        return 1

    if load_model:
        try:
            model = get_whisper_model()
            run_model_smoke_test(model)
            print(
                f"[ok] model inference: {settings.whisper_model} "
                f"on {settings.whisper_device}"
            )
        except Exception as exc:
            print(
                f"[error] Whisper model load failed: {exc}",
                file=sys.stderr,
            )
            return 1

    print(
        f"[ok] model cache: {settings.model_cache_dir}\n"
        f"[ok] transcript output: {settings.knowledge_dir}"
    )
    return 0


def run_model_smoke_test(model) -> None:
    temporary_name = ""
    try:
        with tempfile.NamedTemporaryFile(
            suffix=".wav",
            delete=False,
        ) as temporary_file:
            temporary_name = temporary_file.name
        with wave.open(temporary_name, "wb") as wav_file:
            wav_file.setnchannels(1)
            wav_file.setsampwidth(2)
            wav_file.setframerate(16000)
            wav_file.writeframes(b"\x00\x00" * 16000)
        segments, _ = model.transcribe(
            temporary_name,
            beam_size=1,
            language=settings.whisper_language or "ko",
            vad_filter=False,
            condition_on_previous_text=False,
        )
        list(segments)
    finally:
        if temporary_name:
            Path(temporary_name).unlink(missing_ok=True)


def transcribe_url(
    *,
    source_url: str,
    title_override: str | None,
    output_dir: Path,
    chunk_seconds: int,
    max_chunks: int,
    stop_event: Event,
    start_from_beginning: bool = True,
    on_metadata: Callable[[StreamMetadata, Path], None] | None = None,
    on_progress: ProgressCallback | None = None,
    on_status: StatusCallback | None = None,
) -> Path:
    metadata = probe_stream(source_url)
    title = title_override or metadata.title
    output_dir.mkdir(parents=True, exist_ok=True)
    transcript_path = build_transcript_path(
        output_dir=output_dir,
        author=metadata.author,
        title=title,
        video_id=metadata.video_id,
    )
    if on_metadata:
        on_metadata(metadata, transcript_path)
    if on_status:
        on_status("capturing", "오디오를 수집하고 있습니다.")

    print(
        f"Source: {metadata.author} / {title}\n"
        f"Mode: {'live from start (YouTube DASH)' if metadata.is_live else 'video'}\n"
        f"Output: {transcript_path}"
    )

    all_segments: list[TranscriptSegment] = []
    timeline_seconds = 0.0
    chunk_index = 0
    capture_failures = 0
    first_connection = True

    while not stop_event.is_set():
        if max_chunks > 0 and chunk_index >= max_chunks:
            break

        try:
            with ContinuousCaptureSession.start(
                source_url=source_url,
                capture_seconds=chunk_seconds,
                run_id=0,
                start_from_beginning=metadata.is_live
                and start_from_beginning
                and first_connection,
            ) as capture_session:
                first_connection = False
                session_chunk_index = 0
                while not stop_event.is_set():
                    if max_chunks > 0 and chunk_index >= max_chunks:
                        stop_event.set()
                        break

                    audio_path = capture_session.wait_for_completed_chunk(
                        session_chunk_index,
                        should_stop=stop_event.is_set,
                    )
                    if audio_path is None:
                        if stop_event.is_set() or not metadata.is_live:
                            return finalize_transcript(
                                transcript_path,
                                all_segments,
                            )
                        live_state = probe_youtube_live_state(source_url)
                        if live_state is False:
                            if on_status:
                                on_status(
                                    "completed",
                                    "방송 종료를 확인했습니다.",
                                )
                            return finalize_transcript(
                                transcript_path,
                                all_segments,
                            )
                        capture_failures += 1
                        if capture_failures >= max(
                            1, settings.rolling_capture_retries
                        ):
                            return finalize_transcript(
                                transcript_path,
                                all_segments,
                            )
                        print(
                            "Live connection ended; reconnecting "
                            f"({capture_failures}/"
                            f"{settings.rolling_capture_retries})..."
                        )
                        time.sleep(settings.rolling_retry_seconds)
                        break

                    try:
                        transcription = transcribe_captured_audio(
                            audio_path=audio_path,
                            offset_seconds=timeline_seconds,
                        )
                    finally:
                        audio_path.unlink(missing_ok=True)

                    capture_failures = 0
                    all_segments.extend(transcription.segments)
                    timeline_seconds += max(
                        0.0, transcription.duration_seconds or 0.0
                    )
                    chunk_index += 1
                    session_chunk_index += 1
                    cleaned_segments = suppress_midstream_outro_hallucinations(
                        all_segments
                    )
                    write_transcript(transcript_path, cleaned_segments)
                    if on_progress:
                        on_progress(
                            transcript_path,
                            list(cleaned_segments),
                            timeline_seconds,
                            chunk_index,
                        )
                    if capture_session.source_has_ended and on_status:
                        on_status(
                            "draining",
                            "방송 종료 · 남은 청크를 전사하고 있습니다.",
                        )
                    print(
                        f"chunk={chunk_index} "
                        f"captured={format_duration(timeline_seconds)} "
                        f"segments={len(transcription.segments)}"
                    )
        except CaptureError as exc:
            if metadata.is_live and is_confirmed_stream_end(exc):
                break
            if (
                metadata.is_live
                and probe_youtube_live_state(source_url) is False
            ):
                break
            capture_failures += 1
            if capture_failures >= max(
                1, settings.rolling_capture_retries
            ):
                if all_segments:
                    LOGGER.warning(
                        "capture unavailable; preserving partial transcript: %s",
                        exc,
                    )
                    break
                raise
            LOGGER.warning(
                "capture failed; retrying %s/%s: %s",
                capture_failures,
                settings.rolling_capture_retries,
                exc,
            )
            if on_status:
                on_status(
                    "reconnecting",
                    f"연결이 끊겨 재시도합니다: {exc}",
                )
            time.sleep(settings.rolling_retry_seconds)

    completed_path = finalize_transcript(transcript_path, all_segments)
    if on_status:
        on_status("completed", "전사가 끝났습니다.")
    return completed_path


def probe_stream(source_url: str) -> StreamMetadata:
    streamlink_bin = require_binary("streamlink")
    result = subprocess.run(
        [streamlink_bin, "--json", source_url, settings.streamlink_quality],
        capture_output=True,
        text=True,
        timeout=30,
        check=False,
    )
    if result.returncode != 0:
        raise RuntimeError(
            result.stderr.strip()
            or result.stdout.strip()
            or "No playable stream was found."
        )
    payload: dict[str, Any] = json.loads(result.stdout)
    metadata = payload.get("metadata") or {}
    return StreamMetadata(
        video_id=str(metadata.get("id") or extract_video_id(source_url)),
        title=str(metadata.get("title") or "YouTube transcription"),
        author=str(metadata.get("author") or "YouTube"),
        is_live=streamlink_payload_is_live(payload),
    )


def extract_video_id(source_url: str) -> str:
    parsed = urlparse(source_url)
    if parsed.netloc.lower().endswith("youtu.be"):
        return parsed.path.strip("/") or "video"
    query_id = parse_qs(parsed.query).get("v")
    if query_id:
        return query_id[0]
    return "video"


def build_transcript_path(
    *,
    output_dir: Path,
    author: str,
    title: str,
    video_id: str,
) -> Path:
    stamp = datetime.now().strftime("%Y%m%d-%H%M%S")
    filename = (
        f"{stamp}-transcript-"
        f"{sanitize_filename(author)}-"
        f"{sanitize_filename(title)}-"
        f"{sanitize_filename(video_id)}.txt"
    )
    return output_dir / filename


def sanitize_filename(value: str) -> str:
    cleaned = "".join(
        char if char.isalnum() or char in {"-", "_"} else "-"
        for char in value.lower()
    )
    while "--" in cleaned:
        cleaned = cleaned.replace("--", "-")
    return cleaned.strip("-") or "untitled"


def write_transcript(
    transcript_path: Path,
    segments: list[TranscriptSegment],
) -> None:
    temporary_path = transcript_path.with_suffix(
        f"{transcript_path.suffix}.tmp"
    )
    temporary_path.write_text(
        format_segments(segments),
        encoding="utf-8",
    )
    temporary_path.replace(transcript_path)


def finalize_transcript(
    transcript_path: Path,
    segments: list[TranscriptSegment],
) -> Path:
    cleaned_segments = suppress_midstream_outro_hallucinations(segments)
    write_transcript(transcript_path, cleaned_segments)
    print(f"Completed with {len(cleaned_segments)} transcript segments.")
    return transcript_path


def format_duration(seconds: float) -> str:
    total = max(0, int(seconds))
    hours, remainder = divmod(total, 3600)
    minutes, seconds = divmod(remainder, 60)
    return f"{hours:02d}:{minutes:02d}:{seconds:02d}"


def is_confirmed_stream_end(error: Exception) -> bool:
    message = str(error).lower()
    return any(
        marker in message
        for marker in (
            "this live event has ended",
            "not currently live",
            "is offline",
        )
    )


def install_signal_handlers(stop_event: Event) -> None:
    def request_stop(_signum, _frame) -> None:
        if not stop_event.is_set():
            print("Stop requested; preserving the transcript...")
            stop_event.set()

    signal.signal(signal.SIGINT, request_stop)
    if hasattr(signal, "SIGTERM"):
        signal.signal(signal.SIGTERM, request_stop)


if __name__ == "__main__":
    raise SystemExit(main())
