from __future__ import annotations

import json
import subprocess
import unittest
from pathlib import Path
from tempfile import TemporaryDirectory
from unittest.mock import patch

from app.manual_transcribe import (
    build_transcript_path,
    extract_video_id,
    probe_stream,
)


class ManualTranscriptionTests(unittest.TestCase):
    def test_extracts_standard_and_short_youtube_ids(self) -> None:
        self.assertEqual(
            extract_video_id(
                "https://www.youtube.com/watch?v=RhP227FIV9A"
            ),
            "RhP227FIV9A",
        )
        self.assertEqual(
            extract_video_id("https://youtu.be/2FOTy7qBClw"),
            "2FOTy7qBClw",
        )

    def test_probe_recognizes_live_hls_metadata(self) -> None:
        completed = subprocess.CompletedProcess(
            args=[],
            returncode=0,
            stdout=json.dumps(
                {
                    "url": (
                        "https://manifest.googlevideo.com/index.m3u8"
                        "?playlist_type/LIVE/yt_live_broadcast"
                    ),
                    "metadata": {
                        "id": "live123",
                        "title": "Daily market",
                        "author": "Finance channel",
                    },
                }
            ),
            stderr="",
        )
        with (
            patch(
                "app.transcriber.shutil.which",
                return_value="streamlink",
            ),
            patch(
                "app.manual_transcribe.subprocess.run",
                return_value=completed,
            ),
        ):
            metadata = probe_stream(
                "https://www.youtube.com/watch?v=live123"
            )

        self.assertTrue(metadata.is_live)
        self.assertEqual(metadata.video_id, "live123")
        self.assertEqual(metadata.author, "Finance channel")

    def test_output_path_is_windows_safe(self) -> None:
        with TemporaryDirectory() as temporary_directory:
            path = build_transcript_path(
                output_dir=Path(temporary_directory),
                author="채널:테스트",
                title="장 마감 / 정리?",
                video_id="abc123",
            )

        self.assertNotIn(":", path.name)
        self.assertNotIn("/", path.name)
        self.assertTrue(path.name.endswith("-abc123.txt"))


if __name__ == "__main__":
    unittest.main()
