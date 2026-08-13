from __future__ import annotations

import os
from dataclasses import dataclass
from pathlib import Path


@dataclass(frozen=True)
class Settings:
    app_env: str = os.getenv("APP_ENV", "development")
    data_dir: Path = Path(os.getenv("DATA_DIR", "/data"))
    database_path: Path = Path(os.getenv("DATABASE_PATH", "/data/app.db"))
    knowledge_dir: Path = Path(os.getenv("KNOWLEDGE_DIR", "/data/knowledge"))
    model_cache_dir: Path = Path(os.getenv("MODEL_CACHE_DIR", "/data/models"))
    poll_seconds: int = int(os.getenv("POLL_SECONDS", "5"))
    watcher_poll_seconds: int = int(os.getenv("WATCHER_POLL_SECONDS", "60"))
    transcriber_mode: str = os.getenv("TRANSCRIBER_MODE", "local_whisper").strip().lower()
    transcriber_fallback_to_stub: bool = os.getenv("TRANSCRIBER_FALLBACK_TO_STUB", "false").lower() == "true"
    rolling_chunk_seconds: int = int(os.getenv("ROLLING_CHUNK_SECONDS", "60"))
    rolling_max_chunks: int = int(os.getenv("ROLLING_MAX_CHUNKS", "0"))
    rolling_capture_retries: int = int(os.getenv("ROLLING_CAPTURE_RETRIES", "3"))
    rolling_retry_seconds: int = int(os.getenv("ROLLING_RETRY_SECONDS", "10"))
    worker_concurrency: int = max(1, int(os.getenv("WORKER_CONCURRENCY", "2")))
    worker_lease_seconds: int = max(120, int(os.getenv("WORKER_LEASE_SECONDS", "300")))
    streamlink_quality: str = os.getenv("STREAMLINK_QUALITY", "best").strip()
    whisper_model: str = os.getenv("WHISPER_MODEL", "large-v3-turbo").strip()
    whisper_device: str = os.getenv("WHISPER_DEVICE", "cuda").strip()
    whisper_compute_type: str = os.getenv("WHISPER_COMPUTE_TYPE", "float16").strip()
    whisper_language: str = os.getenv("WHISPER_LANGUAGE", "").strip()
    whisper_beam_size: int = int(os.getenv("WHISPER_BEAM_SIZE", "5"))
    summary_max_bullets: int = int(os.getenv("SUMMARY_MAX_BULLETS", "8"))
    youtube_api_key: str = os.getenv("YOUTUBE_API_KEY", "").strip()


settings = Settings()
