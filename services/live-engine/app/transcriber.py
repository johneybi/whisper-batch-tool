from __future__ import annotations

import logging
import json
import re
import shutil
import subprocess
import sys
import threading
import time
import wave
from collections import Counter
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from tempfile import NamedTemporaryFile, mkdtemp
from typing import Callable

from .config import settings


LOGGER = logging.getLogger(__name__)
_WHISPER_MODEL = None
_WHISPER_MODEL_LOCK = threading.Lock()
_WHISPER_TRANSCRIBE_LOCK = threading.Lock()
# Generic outro phrases can be hallucinated on quiet live-stream chunks.
# Keep this list intentionally narrow and only suppress phrases proven to be
# in the middle of a longer recording.
_MIDSTREAM_OUTRO_PHRASES = {
    "다음 영상에서 만나요",
    "다음에 만나요",
}
_SUMMARY_STOP_WORDS = {
    "그리고",
    "그래서",
    "그러니까",
    "그런데",
    "대한",
    "때문에",
    "말씀",
    "여러분",
    "오늘",
    "이것",
    "저것",
    "합니다",
    "했습니다",
    "있는",
    "있습니다",
    "하는",
}


@dataclass(frozen=True)
class TranscriptSegment:
    start_seconds: float
    end_seconds: float
    text: str


@dataclass(frozen=True)
class TranscriptionResult:
    transcript_text: str
    engine: str
    segments: list[TranscriptSegment]
    notes: list[str]
    duration_seconds: float | None = None


class TranscriptionError(RuntimeError):
    pass


class CaptureError(TranscriptionError):
    pass


class ContinuousCaptureSession:
    def __init__(
        self,
        *,
        capture_dir: Path,
        stream_proc: subprocess.Popen,
        ffmpeg_proc: subprocess.Popen,
        stream_log,
        ffmpeg_log,
    ) -> None:
        self.capture_dir = capture_dir
        self.stream_proc = stream_proc
        self.ffmpeg_proc = ffmpeg_proc
        self.stream_log = stream_log
        self.ffmpeg_log = ffmpeg_log
        self._ended = False
        self._terminal_error: str | None = None

    @classmethod
    def start(
        cls,
        *,
        source_url: str,
        capture_seconds: int,
        run_id: int,
        start_from_beginning: bool = False,
    ) -> "ContinuousCaptureSession":
        ffmpeg_bin = require_binary("ffmpeg")
        if start_from_beginning:
            source_bin = require_binary("yt-dlp")
            source_cmd = build_ytdlp_live_from_start_command(
                ytdlp_bin=source_bin,
                source_url=source_url,
            )
            source_engine = "yt-dlp-live-from-start"
        else:
            source_bin = require_binary("streamlink")
            source_cmd = build_streamlink_command(
                streamlink_bin=source_bin,
                source_url=source_url,
                quality=settings.streamlink_quality,
                start_from_beginning=False,
            )
            source_engine = "streamlink-live-edge"
        settings.data_dir.mkdir(parents=True, exist_ok=True)
        capture_dir = Path(
            mkdtemp(prefix=f"capture-run-{run_id}-", dir=settings.data_dir)
        )
        stream_log = (capture_dir / "source.log").open("wb")
        ffmpeg_log = (capture_dir / "ffmpeg.log").open("wb")
        output_pattern = capture_dir / "chunk-%06d.wav"
        ffmpeg_cmd = [
            ffmpeg_bin,
            "-y",
            "-hide_banner",
            "-loglevel",
            "error",
            "-i",
            "pipe:0",
            "-map",
            "0:a:0",
            "-vn",
            "-acodec",
            "pcm_s16le",
            "-ac",
            "1",
            "-ar",
            "16000",
            "-f",
            "segment",
            "-segment_time",
            str(capture_seconds),
            "-reset_timestamps",
            "1",
            "-segment_format",
            "wav",
            str(output_pattern),
        ]

        LOGGER.info(
            "starting continuous capture run_id=%s source_engine=%s quality=%s chunk_seconds=%s start_from_beginning=%s",
            run_id,
            source_engine,
            settings.streamlink_quality,
            capture_seconds,
            start_from_beginning,
        )
        stream_proc = subprocess.Popen(
            source_cmd,
            stdout=subprocess.PIPE,
            stderr=stream_log,
            text=False,
        )
        try:
            assert stream_proc.stdout is not None
            ffmpeg_proc = subprocess.Popen(
                ffmpeg_cmd,
                stdin=stream_proc.stdout,
                stdout=subprocess.DEVNULL,
                stderr=ffmpeg_log,
                text=False,
            )
            stream_proc.stdout.close()
        except Exception:
            stream_proc.kill()
            stream_proc.wait()
            stream_log.close()
            ffmpeg_log.close()
            shutil.rmtree(capture_dir, ignore_errors=True)
            raise

        return cls(
            capture_dir=capture_dir,
            stream_proc=stream_proc,
            ffmpeg_proc=ffmpeg_proc,
            stream_log=stream_log,
            ffmpeg_log=ffmpeg_log,
        )

    def wait_for_completed_chunk(
        self,
        chunk_index: int,
        *,
        should_stop: Callable[[], bool],
    ) -> Path | None:
        chunk_path = self.capture_dir / f"chunk-{chunk_index:06d}.wav"
        next_path = self.capture_dir / f"chunk-{chunk_index + 1:06d}.wav"

        while True:
            if should_stop():
                self.stop()
                return None

            if next_path.exists() and _is_nonempty_wav(chunk_path):
                return chunk_path

            if self._ended or self.ffmpeg_proc.poll() is not None:
                if not self._ended:
                    self._record_terminal_state()
                if _is_nonempty_wav(chunk_path):
                    return chunk_path
                if self._terminal_error:
                    error = self._terminal_error
                    self._terminal_error = None
                    raise CaptureError(error)
                return None

            time.sleep(0.5)

    def _record_terminal_state(self) -> None:
        ffmpeg_returncode = self.ffmpeg_proc.wait()
        stream_returncode = self.stream_proc.poll()
        if stream_returncode is None:
            self.stream_proc.terminate()
            try:
                self.stream_proc.wait(timeout=10)
            except subprocess.TimeoutExpired:
                self.stream_proc.kill()
                self.stream_proc.wait()
        self._ended = True
        self.stream_log.flush()
        self.ffmpeg_log.flush()

        if ffmpeg_returncode != 0 or (
            stream_returncode is not None and stream_returncode != 0
        ):
            detail = self._read_error_logs()
            self._terminal_error = (
                "Continuous live capture stopped unexpectedly"
                + (f": {detail}" if detail else "")
            )

    def _read_error_logs(self) -> str:
        messages = []
        for path in (
            self.capture_dir / "ffmpeg.log",
            self.capture_dir / "source.log",
        ):
            if path.exists():
                text = path.read_text(encoding="utf-8", errors="ignore").strip()
                if text:
                    messages.append(text[-1000:])
        return " | ".join(messages)

    @property
    def source_has_ended(self) -> bool:
        """Whether the downloader has stopped while FFmpeg chunks remain."""
        return self.stream_proc.poll() is not None

    def stop(self) -> None:
        for process in (self.ffmpeg_proc, self.stream_proc):
            if process.poll() is None:
                process.terminate()
        for process in (self.ffmpeg_proc, self.stream_proc):
            if process.poll() is None:
                try:
                    process.wait(timeout=10)
                except subprocess.TimeoutExpired:
                    process.kill()
                    process.wait()
        self._ended = True

    def close(self) -> None:
        self.stop()
        self.stream_log.close()
        self.ffmpeg_log.close()
        shutil.rmtree(self.capture_dir, ignore_errors=True)

    def __enter__(self) -> "ContinuousCaptureSession":
        return self

    def __exit__(self, *_args) -> None:
        self.close()


def transcribe_source(*, channel_name: str, title: str, source_url: str) -> TranscriptionResult:
    mode = settings.transcriber_mode
    if mode == "stub":
        return build_stub_transcript(channel_name, title, source_url)
    if mode == "local_whisper":
        return transcribe_with_local_whisper(channel_name=channel_name, title=title, source_url=source_url)
    raise TranscriptionError(f"Unsupported TRANSCRIBER_MODE: {mode}")


def build_stub_transcript(channel_name: str, title: str, source_url: str) -> TranscriptionResult:
    segments = [
        TranscriptSegment(0.0, 5.0, f"Channel: {channel_name}"),
        TranscriptSegment(5.0, 12.0, f"Live title: {title}"),
        TranscriptSegment(12.0, 65.0, "TODO: replace this stub with Streamlink + ffmpeg + faster-whisper output."),
        TranscriptSegment(65.0, 90.0, "TODO: chunk transcript into segments and persist per segment for later summarization."),
        TranscriptSegment(90.0, 95.0, f"Source URL: {source_url}"),
    ]
    return TranscriptionResult(
        transcript_text=format_segments(segments),
        engine="stub",
        segments=segments,
        notes=[
            "Running in stub mode.",
            "Set TRANSCRIBER_MODE=local_whisper to enable local audio capture and faster-whisper transcription.",
        ],
    )


def transcribe_with_local_whisper(*, channel_name: str, title: str, source_url: str) -> TranscriptionResult:
    return transcribe_live_chunk(
        source_url=source_url,
        offset_seconds=0.0,
        capture_seconds=settings.rolling_chunk_seconds,
    )


def transcribe_live_chunk(
    *,
    source_url: str,
    offset_seconds: float,
    capture_seconds: int,
) -> TranscriptionResult:
    streamlink_bin = require_binary("streamlink")
    ffmpeg_bin = require_binary("ffmpeg")
    audio_path = capture_live_audio(
        source_url=source_url,
        streamlink_bin=streamlink_bin,
        ffmpeg_bin=ffmpeg_bin,
        capture_seconds=capture_seconds,
    )
    try:
        result = transcribe_captured_audio(
            audio_path=audio_path,
            offset_seconds=offset_seconds,
        )
    finally:
        if audio_path.exists():
            audio_path.unlink()

    return TranscriptionResult(
        transcript_text=result.transcript_text,
        engine=result.engine,
        segments=result.segments,
        notes=[*result.notes, f"Source URL: {source_url}"],
    )


def require_binary(binary_name: str) -> str:
    resolved = shutil.which(binary_name)
    if not resolved and sys.platform == "win32":
        sibling = Path(sys.executable).with_name(f"{binary_name}.exe")
        if sibling.exists():
            resolved = str(sibling)
    if not resolved:
        raise TranscriptionError(
            f"Required binary `{binary_name}` is not installed or discoverable"
        )
    return resolved


def build_streamlink_command(
    *,
    streamlink_bin: str,
    source_url: str,
    quality: str,
    start_from_beginning: bool,
) -> list[str]:
    command = [streamlink_bin]
    if start_from_beginning:
        command.append("--hls-live-restart")
    command.extend(["--stdout", source_url, quality])
    return command


def build_ytdlp_live_from_start_command(
    *,
    ytdlp_bin: str,
    source_url: str,
) -> list[str]:
    """Build a YouTube live command that follows the full DASH timeline.

    Streamlink's HLS restart can only rewind to the first segment exposed in
    its short HLS manifest.  yt-dlp's YouTube-specific live-from-start mode
    follows the DASH timeline used for historical live fragments instead.
    """
    return [
        ytdlp_bin,
        "--live-from-start",
        "--format",
        "bestaudio/best",
        "--output",
        "-",
        "--no-part",
        "--no-progress",
        "--quiet",
        "--fragment-retries",
        "infinite",
        "--retry-sleep",
        "fragment:1",
        source_url,
    ]


def probe_youtube_live_state(source_url: str) -> bool | None:
    """Return True for live, False for ended/VOD, and None if uncertain."""
    streamlink_bin = require_binary("streamlink")
    result = subprocess.run(
        [streamlink_bin, "--json", source_url, settings.streamlink_quality],
        capture_output=True,
        text=True,
        timeout=30,
        check=False,
    )
    if result.returncode != 0:
        message = (result.stderr or result.stdout or "").lower()
        if any(
            marker in message
            for marker in (
                "this live event has ended",
                "not currently live",
                "is offline",
            )
        ):
            return False
        return None
    try:
        payload = json.loads(result.stdout)
    except json.JSONDecodeError:
        return None
    return streamlink_payload_is_live(payload)


def streamlink_payload_is_live(payload: dict) -> bool:
    resolved_url = " ".join(
        str(payload.get(key) or "") for key in ("url", "master")
    ).lower()
    return any(
        marker in resolved_url
        for marker in (
            "playlist_type/live",
            "playlist_type=dvr",
            "/live/1",
            "yt_live_broadcast",
        )
    )


def capture_live_audio(
    *,
    source_url: str,
    streamlink_bin: str,
    ffmpeg_bin: str,
    capture_seconds: int,
) -> Path:
    settings.data_dir.mkdir(parents=True, exist_ok=True)
    with NamedTemporaryFile(
        prefix="capture-",
        suffix=".wav",
        dir=settings.data_dir,
        delete=False,
    ) as temp_file:
        output_path = Path(temp_file.name)

    stream_cmd = build_streamlink_command(
        streamlink_bin=streamlink_bin,
        source_url=source_url,
        quality=settings.streamlink_quality,
        start_from_beginning=False,
    )
    ffmpeg_cmd = [
        ffmpeg_bin,
        "-y",
        "-hide_banner",
        "-loglevel",
        "error",
        "-i",
        "pipe:0",
        "-vn",
        "-acodec",
        "pcm_s16le",
        "-ac",
        "1",
        "-ar",
        "16000",
        "-t",
        str(capture_seconds),
        str(output_path),
    ]

    LOGGER.info("capturing audio with streamlink quality=%s seconds=%s", settings.streamlink_quality, capture_seconds)
    stream_proc = subprocess.Popen(
        stream_cmd,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        text=False,
    )
    try:
        assert stream_proc.stdout is not None
        ffmpeg_result = subprocess.run(
            ffmpeg_cmd,
            stdin=stream_proc.stdout,
            capture_output=True,
            timeout=capture_seconds + 90,
            text=True,
            check=False,
        )
        stream_proc.stdout.close()
        stream_proc.terminate()
        try:
            _, stream_stderr = stream_proc.communicate(timeout=10)
        except subprocess.TimeoutExpired:
            stream_proc.kill()
            _, stream_stderr = stream_proc.communicate()
    except subprocess.TimeoutExpired as exc:
        stream_proc.kill()
        if output_path.exists():
            output_path.unlink()
        raise CaptureError("Timed out while capturing the live audio window") from exc
    except Exception:
        stream_proc.kill()
        if output_path.exists():
            output_path.unlink()
        raise

    if ffmpeg_result.returncode != 0:
        if output_path.exists():
            output_path.unlink()
        raise CaptureError(
            "ffmpeg failed while capturing live audio: "
            f"{ffmpeg_result.stderr.strip() or stream_stderr.decode('utf-8', errors='ignore').strip()}"
        )

    if not output_path.exists() or output_path.stat().st_size == 0:
        raise CaptureError("Audio capture completed but produced an empty WAV file")

    return output_path


def transcribe_audio(audio_path: Path) -> list[TranscriptSegment]:
    model = get_whisper_model()
    language = settings.whisper_language or None
    # Multiple live captures may run concurrently, but a single model instance
    # is shared to avoid loading large-v3-turbo twice on an 8 GB GPU.
    with _WHISPER_TRANSCRIBE_LOCK:
        segments, _ = model.transcribe(
            str(audio_path),
            beam_size=settings.whisper_beam_size,
            language=language,
            vad_filter=True,
            condition_on_previous_text=False,
        )
        formatted_segments: list[TranscriptSegment] = []
        for segment in segments:
            text = segment.text.strip()
            if not text:
                continue
            formatted_segments.append(
                TranscriptSegment(
                    start_seconds=float(segment.start),
                    end_seconds=float(segment.end),
                    text=text,
                )
            )
    return formatted_segments


def transcribe_captured_audio(
    *,
    audio_path: Path,
    offset_seconds: float,
) -> TranscriptionResult:
    local_segments = transcribe_audio(audio_path)
    duration_seconds = wav_duration_seconds(audio_path)
    segments = offset_and_clamp_segments(
        local_segments,
        offset_seconds=offset_seconds,
        duration_seconds=duration_seconds,
    )
    return TranscriptionResult(
        transcript_text=format_segments(segments),
        engine="local_whisper",
        segments=segments,
        notes=[
            f"Captured {duration_seconds:.1f} seconds of live audio.",
            f"Transcribed with model `{settings.whisper_model}` on device `{settings.whisper_device}`.",
        ],
        duration_seconds=duration_seconds,
    )


def offset_and_clamp_segments(
    segments: list[TranscriptSegment],
    *,
    offset_seconds: float,
    duration_seconds: float,
) -> list[TranscriptSegment]:
    adjusted = []
    for segment in segments:
        local_start = min(max(0.0, segment.start_seconds), duration_seconds)
        local_end = min(
            max(local_start, segment.end_seconds),
            duration_seconds,
        )
        adjusted.append(
            TranscriptSegment(
                start_seconds=local_start + offset_seconds,
                end_seconds=local_end + offset_seconds,
                text=segment.text,
            )
        )
    return adjusted


def wav_duration_seconds(audio_path: Path) -> float:
    try:
        with wave.open(str(audio_path), "rb") as wav_file:
            frame_rate = wav_file.getframerate()
            if frame_rate <= 0:
                return 0.0
            return wav_file.getnframes() / frame_rate
    except (wave.Error, OSError):
        return 0.0


def _is_nonempty_wav(audio_path: Path) -> bool:
    return (
        audio_path.exists()
        and audio_path.stat().st_size > 44
        and wav_duration_seconds(audio_path) > 0.0
    )


def get_whisper_model():
    global _WHISPER_MODEL
    if _WHISPER_MODEL is None:
        with _WHISPER_MODEL_LOCK:
            if _WHISPER_MODEL is None:
                from faster_whisper import WhisperModel

                LOGGER.info(
                    "loading faster-whisper model=%s device=%s compute_type=%s",
                    settings.whisper_model,
                    settings.whisper_device,
                    settings.whisper_compute_type,
                )
                _WHISPER_MODEL = WhisperModel(
                    settings.whisper_model,
                    device=settings.whisper_device,
                    compute_type=settings.whisper_compute_type,
                    download_root=str(settings.model_cache_dir),
                )
    return _WHISPER_MODEL


def format_segments(segments: list[TranscriptSegment]) -> str:
    return "\n".join(
        f"[{format_timestamp(segment.start_seconds)} - {format_timestamp(segment.end_seconds)}] {segment.text}"
        for segment in segments
    )


def suppress_midstream_outro_hallucinations(
    segments: list[TranscriptSegment],
    *,
    tail_grace_seconds: float = 90.0,
) -> list[TranscriptSegment]:
    """Remove isolated generic outro phrases once later audio proves them mid-stream."""
    if not segments:
        return []
    latest_end = max(segment.end_seconds for segment in segments)
    cleaned: list[TranscriptSegment] = []
    for segment in segments:
        normalized = re.sub(r"[.!?。！？\s]+$", "", segment.text.strip())
        is_outro = normalized in _MIDSTREAM_OUTRO_PHRASES
        is_midstream = segment.end_seconds < latest_end - tail_grace_seconds
        if is_outro and is_midstream:
            LOGGER.info(
                "suppressing midstream outro hallucination at %.1fs: %s",
                segment.start_seconds,
                segment.text,
            )
            continue
        cleaned.append(segment)
    return cleaned


def format_timestamp(seconds: float) -> str:
    total = max(0, int(seconds))
    minutes, remainder = divmod(total, 60)
    hours, minutes = divmod(minutes, 60)
    return f"{hours:02d}:{minutes:02d}:{remainder:02d}"


def build_summary_markdown(
    *,
    channel_name: str,
    title: str,
    source_url: str,
    transcription: TranscriptionResult,
    chunk_count: int | None = None,
    is_live: bool = False,
) -> str:
    timestamp = datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M UTC")
    summary_lines = extract_summary_lines(
        transcription.segments,
        max_lines=settings.summary_max_bullets,
    )
    summary_lines = summary_lines or ["No spoken content was detected in the captured window."]
    bullets = "\n".join(f"- {line}" for line in summary_lines)
    notes = "\n".join(f"- {note}" for note in transcription.notes)
    return "\n".join(
        [
            f"# {title}",
            "",
            f"- Channel: {channel_name}",
            f"- Captured at: {timestamp}",
            f"- Source: {source_url}",
            f"- Engine: {transcription.engine}",
            f"- Chunks: {chunk_count}" if chunk_count is not None else "",
            f"- State: {'live / updating' if is_live else 'completed'}",
            "",
            "## Local Summary",
            "",
            bullets,
            "",
            "## Worker Notes",
            "",
            notes,
            "",
        ]
    )


def extract_summary_lines(
    segments: list[TranscriptSegment],
    *,
    max_lines: int,
) -> list[str]:
    """Select representative transcript lines without an external API or model."""
    candidates = [segment.text.strip() for segment in segments if len(segment.text.strip()) >= 12]
    if len(candidates) <= max_lines:
        return candidates

    tokenized = [_summary_tokens(text) for text in candidates]
    frequencies = Counter(token for tokens in tokenized for token in set(tokens))
    scored: list[tuple[float, int, str]] = []
    for index, (text, tokens) in enumerate(zip(candidates, tokenized)):
        unique_tokens = set(tokens)
        lexical_score = sum(frequencies[token] for token in unique_tokens)
        length_penalty = max(1.0, len(tokens) ** 0.5)
        position_bonus = 1.15 if index in {0, len(candidates) - 1} else 1.0
        scored.append((lexical_score * position_bonus / length_penalty, index, text))

    selected = sorted(scored, reverse=True)[:max_lines]
    return [text for _, _, text in sorted(selected, key=lambda item: item[1])]


def _summary_tokens(text: str) -> list[str]:
    return [
        token
        for token in re.findall(r"[0-9A-Za-z가-힣]{2,}", text.lower())
        if token not in _SUMMARY_STOP_WORDS
    ]
