from pathlib import Path
import tempfile
import unittest

from transcriber_core import (
    TranscriptionOptions,
    _capture_whisper_frame_progress,
    _format_timestamp,
    discover_media_files,
    write_outputs,
)


class TranscriberCoreTests(unittest.TestCase):
    def test_format_timestamp_rounds_to_milliseconds(self) -> None:
        self.assertEqual(_format_timestamp(3661.2344), "01:01:01,234")
        self.assertEqual(_format_timestamp(1.9996, "."), "00:00:02.000")

    def test_discover_media_files_filters_supported_extensions(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            media = root / "clip.MP4"
            nested = root / "nested"
            nested.mkdir()
            nested_media = nested / "audio.wav"
            ignored = root / "notes.txt"

            media.write_bytes(b"")
            nested_media.write_bytes(b"")
            ignored.write_text("not media", encoding="utf-8")

            self.assertEqual(discover_media_files(root, recursive=False), [media])
            self.assertEqual(discover_media_files(root, recursive=True), [media, nested_media])

    def test_write_outputs_creates_requested_formats_and_avoids_collisions(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            source = root / "meeting.wav"
            source.write_bytes(b"")
            (root / "meeting.txt").write_text("existing", encoding="utf-8")

            result = {
                "text": "hello world",
                "language": "en",
                "segments": [
                    {"start": 0.0, "end": 1.25, "text": "hello"},
                    {"start": 1.25, "end": 2.5, "text": "world"},
                ],
            }
            options = TranscriptionOptions(output_formats=["txt", "srt", "json"], output_dir=root)

            outputs = write_outputs(source, result, options, elapsed=3.2)

            self.assertEqual(
                [path.name for path in outputs],
                ["meeting_1.txt", "meeting.srt", "meeting.json"],
            )
            self.assertIn("hello world", (root / "meeting_1.txt").read_text(encoding="utf-8"))
            self.assertIn("00:00:00,000 --> 00:00:01,250", (root / "meeting.srt").read_text(encoding="utf-8"))
            self.assertIn('"language": "en"', (root / "meeting.json").read_text(encoding="utf-8"))

    def test_capture_whisper_frame_progress_reports_tqdm_updates(self) -> None:
        import importlib

        transcribe_module = importlib.import_module("whisper.transcribe")
        original_tqdm = transcribe_module.tqdm.tqdm
        events: list[tuple[int, int]] = []

        with _capture_whisper_frame_progress(lambda current, total: events.append((current, total))):
            with transcribe_module.tqdm.tqdm(total=10, disable=True) as progress:
                progress.update(3)
                progress.update(4)

        self.assertEqual(events, [(0, 10), (3, 10), (7, 10)])
        self.assertIs(transcribe_module.tqdm.tqdm, original_tqdm)


if __name__ == "__main__":
    unittest.main()
