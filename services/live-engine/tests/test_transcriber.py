from __future__ import annotations

import json
import subprocess
import unittest
import wave
from pathlib import Path
from tempfile import TemporaryDirectory
from unittest.mock import patch

from app.transcriber import (
    TranscriptSegment,
    build_streamlink_command,
    build_ytdlp_live_from_start_command,
    extract_summary_lines,
    format_segments,
    format_timestamp,
    offset_and_clamp_segments,
    probe_youtube_live_state,
    streamlink_payload_is_live,
    suppress_midstream_outro_hallucinations,
    wav_duration_seconds,
)


class TranscriberFormattingTests(unittest.TestCase):
    def test_suppresses_outro_phrase_only_after_later_audio(self) -> None:
        segments = [
            TranscriptSegment(100.0, 102.0, "다음 영상에서 만나요."),
            TranscriptSegment(120.0, 150.0, "중간에 이어지는 시장 이야기"),
            TranscriptSegment(200.0, 210.0, "다음 영상에서 만나요."),
        ]

        cleaned = suppress_midstream_outro_hallucinations(segments)

        self.assertEqual(
            [(segment.start_seconds, segment.text) for segment in cleaned],
            [(120.0, "중간에 이어지는 시장 이야기"), (200.0, "다음 영상에서 만나요.")],
        )

    def test_keeps_non_exact_outro_text(self) -> None:
        segments = [
            TranscriptSegment(10.0, 12.0, "다음 영상에서 만나요, 감사합니다."),
            TranscriptSegment(200.0, 210.0, "시장 이야기"),
        ]

        self.assertEqual(suppress_midstream_outro_hallucinations(segments), segments)

    def test_format_timestamp_supports_offsets_longer_than_one_hour(self) -> None:
        self.assertEqual(format_timestamp(3723.9), "01:02:03")

    def test_format_segments_preserves_rolling_offsets(self) -> None:
        segments = [
            TranscriptSegment(60.0, 64.5, "두 번째 청크"),
            TranscriptSegment(65.0, 70.0, "계속되는 전사"),
        ]

        self.assertEqual(
            format_segments(segments),
            "\n".join(
                [
                    "[00:01:00 - 00:01:04] 두 번째 청크",
                    "[00:01:05 - 00:01:10] 계속되는 전사",
                ]
            ),
        )

    def test_extract_summary_keeps_source_order(self) -> None:
        segments = [
            TranscriptSegment(0, 1, "반도체 업종의 실적 전망이 개선되고 있습니다"),
            TranscriptSegment(1, 2, "오늘 시장은 전반적으로 조용합니다"),
            TranscriptSegment(2, 3, "반도체 기업의 수출 증가가 이어지고 있습니다"),
            TranscriptSegment(3, 4, "배터리 기업도 새로운 계약을 발표했습니다"),
        ]

        selected = extract_summary_lines(segments, max_lines=2)

        self.assertEqual(len(selected), 2)
        self.assertEqual(
            selected,
            sorted(selected, key=lambda text: [segment.text for segment in segments].index(text)),
        )

    def test_wav_duration_uses_audio_frames(self) -> None:
        with TemporaryDirectory() as temporary_directory:
            audio_path = Path(temporary_directory) / "chunk.wav"
            with wave.open(str(audio_path), "wb") as wav_file:
                wav_file.setnchannels(1)
                wav_file.setsampwidth(2)
                wav_file.setframerate(16000)
                wav_file.writeframes(b"\x00\x00" * 24000)

            self.assertEqual(wav_duration_seconds(audio_path), 1.5)

    def test_chunk_segments_are_clamped_before_offset(self) -> None:
        segments = [
            TranscriptSegment(18.0, 21.0, "청크 끝 문장"),
        ]

        adjusted = offset_and_clamp_segments(
            segments,
            offset_seconds=20.0,
            duration_seconds=20.0,
        )

        self.assertEqual(
            adjusted,
            [TranscriptSegment(38.0, 40.0, "청크 끝 문장")],
        )

    def test_streamlink_command_uses_live_edge(self) -> None:
        command = build_streamlink_command(
            streamlink_bin="streamlink",
            source_url="https://youtube.com/watch?v=live",
            quality="best",
            start_from_beginning=False,
        )

        self.assertEqual(
            command,
            [
                "streamlink",
                "--stdout",
                "https://youtube.com/watch?v=live",
                "best",
            ],
        )

    def test_ytdlp_command_requests_actual_live_start(self) -> None:
        command = build_ytdlp_live_from_start_command(
            ytdlp_bin="yt-dlp",
            source_url="https://youtube.com/watch?v=live",
        )

        self.assertIn("--live-from-start", command)
        self.assertEqual(command[-1], "https://youtube.com/watch?v=live")
        self.assertNotIn("--hls-live-restart", command)

    def test_streamlink_payload_distinguishes_live_from_vod(self) -> None:
        self.assertTrue(
            streamlink_payload_is_live(
                {"url": "https://manifest.example/live/1/index.m3u8"}
            )
        )
        self.assertFalse(
            streamlink_payload_is_live(
                {"url": "https://video.example/archive.mp4"}
            )
        )

    def test_probe_reports_ended_when_streamlink_returns_vod(self) -> None:
        completed = subprocess.CompletedProcess(
            args=[],
            returncode=0,
            stdout=json.dumps(
                {"url": "https://video.example/archive.mp4"}
            ),
            stderr="",
        )
        with (
            patch("app.transcriber.require_binary", return_value="streamlink"),
            patch("app.transcriber.subprocess.run", return_value=completed),
        ):
            self.assertFalse(
                probe_youtube_live_state("https://youtube.com/watch?v=ended")
            )

    def test_probe_keeps_transient_failure_uncertain(self) -> None:
        completed = subprocess.CompletedProcess(
            args=[],
            returncode=1,
            stdout="",
            stderr="temporary network error",
        )
        with (
            patch("app.transcriber.require_binary", return_value="streamlink"),
            patch("app.transcriber.subprocess.run", return_value=completed),
        ):
            self.assertIsNone(
                probe_youtube_live_state("https://youtube.com/watch?v=live")
            )


if __name__ == "__main__":
    unittest.main()
