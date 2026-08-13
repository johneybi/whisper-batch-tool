from __future__ import annotations

import queue
import threading
import time
import unittest
from pathlib import Path
from unittest.mock import patch

from app.live_view import EventBroker, LiveCoordinator, LiveRun, _sse
from app.manual_transcribe import StreamMetadata
from app.transcriber import TranscriptSegment


def wait_until(predicate, timeout: float = 2.0) -> None:
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        if predicate():
            return
        time.sleep(0.01)
    raise AssertionError("condition was not reached before timeout")


class EventBrokerTests(unittest.TestCase):
    def test_broker_delivers_run_event(self) -> None:
        broker = EventBroker()
        subscriber = broker.subscribe()
        event = {"type": "run", "run": {"id": "abc", "sequence": 3}}

        broker.publish(event)

        self.assertEqual(subscriber.get_nowait(), event)
        broker.unsubscribe(subscriber)
        with self.assertRaises(queue.Empty):
            subscriber.get_nowait()

    def test_sse_includes_id_and_unicode_json(self) -> None:
        encoded = _sse(
            {"type": "run", "message": "전사 중"},
            event_id="abc:2",
        )

        self.assertTrue(encoded.startswith("id: abc:2\n"))
        self.assertIn("전사 중", encoded)
        self.assertTrue(encoded.endswith("\n\n"))


class LiveCoordinatorTests(unittest.TestCase):
    def test_run_snapshot_preserves_live_start_choice(self) -> None:
        run = LiveRun(
            id="run-now",
            source_url="https://youtu.be/live",
            title_override=None,
            chunk_seconds=30,
            start_from_beginning=False,
        )

        self.assertFalse(run.snapshot()["start_from_beginning"])

    def test_two_runs_execute_while_third_waits(self) -> None:
        coordinator = LiveCoordinator(max_captures=2)
        started: list[str] = []
        release = threading.Event()
        started_lock = threading.Lock()

        def fake_transcribe_url(**kwargs):
            source_url = kwargs["source_url"]
            with started_lock:
                started.append(source_url)
            metadata = StreamMetadata(
                video_id=source_url.rsplit("/", 1)[-1],
                title=source_url,
                author="test",
                is_live=True,
            )
            output_path = Path("transcript.txt")
            kwargs["on_metadata"](metadata, output_path)
            kwargs["on_progress"](
                output_path,
                [TranscriptSegment(0, 1, source_url)],
                1.0,
                1,
            )
            release.wait(timeout=2)
            return output_path

        try:
            with patch(
                "app.live_view.transcribe_url",
                side_effect=fake_transcribe_url,
            ):
                run_ids = [
                    coordinator.create_run(
                        source_url=f"https://youtu.be/{index}",
                        title=None,
                        chunk_seconds=30,
                    )["id"]
                    for index in range(3)
                ]
                wait_until(lambda: len(started) == 2)

                self.assertEqual(
                    coordinator.get_run(run_ids[2])["status"],
                    "queued",
                )
                release.set()
                wait_until(lambda: len(started) == 3)
                wait_until(
                    lambda: all(
                        coordinator.get_run(run_id)["status"]
                        == "completed"
                        for run_id in run_ids
                    )
                )
                transcripts = [
                    coordinator.get_run(run_id)["transcript"]
                    for run_id in run_ids
                ]
                self.assertTrue(
                    all("https://youtu.be/" in text for text in transcripts)
                )
        finally:
            release.set()
            coordinator.shutdown()

    def test_stop_cancels_a_queued_run(self) -> None:
        coordinator = LiveCoordinator(max_captures=1)
        release = threading.Event()

        def fake_transcribe_url(**kwargs):
            release.wait(timeout=2)
            return Path("transcript.txt")

        try:
            with patch(
                "app.live_view.transcribe_url",
                side_effect=fake_transcribe_url,
            ):
                coordinator.create_run(
                    source_url="https://youtu.be/active",
                    title=None,
                    chunk_seconds=30,
                )
                queued_id = coordinator.create_run(
                    source_url="https://youtu.be/queued",
                    title=None,
                    chunk_seconds=30,
                )["id"]

                stopped = coordinator.stop_run(queued_id)

                self.assertEqual(stopped["status"], "stopped")
        finally:
            release.set()
            coordinator.shutdown()


if __name__ == "__main__":
    unittest.main()
