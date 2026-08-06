from pathlib import Path
import tempfile
import unittest

import runtime_manager
from transcriber_core import (
    TranscriptionOptions,
    _build_transcribe_kwargs,
    _capture_whisper_frame_progress,
    _format_timestamp,
    _write_atomic,
    discover_media_files,
    validate_transcription_options,
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

    def test_validate_transcription_options_normalizes_safe_values(self) -> None:
        options = validate_transcription_options(
            TranscriptionOptions(
                model_name="small",
                language=" ko ",
                task="transcribe",
                output_formats=["TXT", "srt", "txt"],
                device="auto",
                temperature=0,
            )
        )

        self.assertEqual(options.model_name, "small")
        self.assertEqual(options.language, "ko")
        self.assertEqual(options.task, "transcribe")
        self.assertEqual(options.output_formats, ["txt", "srt"])
        self.assertEqual(options.device, "auto")
        self.assertEqual(options.temperature, 0.0)
        self.assertEqual(options.no_speech_threshold, 0.6)
        self.assertEqual(options.logprob_threshold, -1.0)
        self.assertEqual(options.compression_ratio_threshold, 2.4)

    def test_validate_transcription_options_rejects_invalid_values(self) -> None:
        invalid_cases = [
            (TranscriptionOptions(model_name="bad-model"), "Unsupported model_name"),
            (TranscriptionOptions(task="summarize"), "Unsupported task"),
            (TranscriptionOptions(device="gpu"), "Unsupported device"),
            (TranscriptionOptions(output_formats=[]), "Select at least one output format"),
            (TranscriptionOptions(output_formats=["exe"]), "Unsupported output format"),
            (TranscriptionOptions(language="../../secret"), "language must be a valid language code"),
            (TranscriptionOptions(overwrite="yes"), "overwrite must be a boolean"),
            (TranscriptionOptions(condition_on_previous_text="yes"), "condition_on_previous_text must be a boolean"),
            (TranscriptionOptions(no_speech_threshold="0.6"), "no_speech_threshold must be a number or None"),
            (TranscriptionOptions(no_speech_threshold=-0.1), "no_speech_threshold must be 0.0 or greater"),
            (TranscriptionOptions(compression_ratio_threshold=-0.1), "compression_ratio_threshold must be 0.0 or greater"),
        ]

        for options, message in invalid_cases:
            with self.subTest(message=message):
                with self.assertRaisesRegex(ValueError, message):
                    validate_transcription_options(options)

    def test_build_transcribe_kwargs_keeps_repetition_guards_visible(self) -> None:
        options = validate_transcription_options(
            TranscriptionOptions(
                task="transcribe",
                temperature=0.0,
                condition_on_previous_text=False,
                no_speech_threshold=0.5,
                logprob_threshold=-0.75,
                compression_ratio_threshold=2.0,
            )
        )

        kwargs = _build_transcribe_kwargs(options, language="ko", fp16=True)

        self.assertEqual(kwargs["language"], "ko")
        self.assertEqual(kwargs["task"], "transcribe")
        self.assertTrue(kwargs["fp16"])
        self.assertFalse(kwargs["condition_on_previous_text"])
        self.assertEqual(kwargs["no_speech_threshold"], 0.5)
        self.assertEqual(kwargs["logprob_threshold"], -0.75)
        self.assertEqual(kwargs["compression_ratio_threshold"], 2.0)

    def test_write_outputs_rejects_invalid_formats_instead_of_ignoring_them(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            source = root / "meeting.wav"
            source.write_bytes(b"")
            options = TranscriptionOptions(output_formats=["txt", "exe"], output_dir=root)

            with self.assertRaisesRegex(ValueError, "Unsupported output format"):
                write_outputs(source, {"text": "", "segments": []}, options, elapsed=0)

    def test_write_atomic_does_not_leave_final_or_temp_file_on_failure(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            final_path = root / "meeting.txt"

            def failing_writer(path: Path) -> None:
                path.write_text("partial", encoding="utf-8")
                raise RuntimeError("disk full")

            with self.assertRaisesRegex(RuntimeError, "disk full"):
                _write_atomic(final_path, failing_writer)

            self.assertFalse(final_path.exists())
            self.assertEqual(list(root.glob("*.tmp")), [])

    def test_write_atomic_replaces_existing_file_only_after_success(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            final_path = root / "meeting.txt"
            final_path.write_text("old", encoding="utf-8")

            def successful_writer(path: Path) -> None:
                path.write_text("new", encoding="utf-8")

            _write_atomic(final_path, successful_writer)

            self.assertEqual(final_path.read_text(encoding="utf-8"), "new")

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

    def test_runtime_selection_uses_appdata_override(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            old_value = runtime_manager.os.environ.get("WHISPER_BATCH_APPDATA")
            runtime_manager.os.environ["WHISPER_BATCH_APPDATA"] = temp_dir
            try:
                self.assertEqual(runtime_manager.get_selected_runtime(), "bundled")
                runtime_manager.set_selected_runtime("cuda")
                self.assertEqual(runtime_manager.get_selected_runtime(), "cuda")
                activation = runtime_manager.activate_selected_runtime()
                self.assertEqual(activation.selected, "cuda")
                self.assertFalse(activation.active)
            finally:
                if old_value is None:
                    runtime_manager.os.environ.pop("WHISPER_BATCH_APPDATA", None)
                else:
                    runtime_manager.os.environ["WHISPER_BATCH_APPDATA"] = old_value


if __name__ == "__main__":
    unittest.main()
