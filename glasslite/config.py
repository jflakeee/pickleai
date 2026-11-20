from __future__ import annotations

import os
from dataclasses import dataclass, field
from pathlib import Path


def _env(name: str, default: str) -> str:
    return os.environ.get(f"GLASSLITE_{name}", default)


@dataclass(frozen=True)
class Config:
    home: Path = field(default_factory=lambda: Path(_env("HOME", str(Path.home() / ".glasslite"))).expanduser())
    screen_interval: float = float(_env("SCREEN_INTERVAL", "10"))     # seconds between screenshots
    screen_diff_threshold: float = float(_env("SCREEN_DIFF", "0.02"))  # min fraction of changed pixels to keep
    screen_max_width: int = int(_env("SCREEN_MAX_WIDTH", "1568"))      # downscale before saving (vision-friendly)
    audio_chunk: float = float(_env("AUDIO_CHUNK", "15"))             # seconds per transcription chunk
    whisper_model: str = _env("WHISPER_MODEL", "small")
    whisper_language: str | None = os.environ.get("GLASSLITE_WHISPER_LANG") or None  # e.g. "ko"; None = auto
    claude_model: str = _env("CLAUDE_MODEL", "claude-opus-5-5")
    retention_days: int = int(_env("RETENTION_DAYS", "7"))

    @property
    def db_path(self) -> Path:
        return self.home / "glasslite.db"

    @property
    def notes_dir(self) -> Path:
        return self.home / "notes"

    @property
    def shots_dir(self) -> Path:
        return self.home / "shots"

    def ensure_dirs(self) -> None:
        self.shots_dir.mkdir(parents=True, exist_ok=True)
