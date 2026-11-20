"""Background thread: every N minutes, summarize the window via Claude API if new speech arrived."""
from __future__ import annotations

import logging
import threading
import time

from .db import Store

log = logging.getLogger(__name__)


class AutoSummarizer(threading.Thread):
    def __init__(self, assistant, store: Store, stop: threading.Event, every_min: float,
                 min_segments: int = 3, max_images: int = 2):
        super().__init__(daemon=True, name="autosummary")
        self.ai, self.store, self.stop_ev = assistant, store, stop
        self.every_min, self.min_segments, self.max_images = every_min, min_segments, max_images
        self.last = time.time()

    def tick(self, now: float | None = None) -> str | None:
        """Summarize since the last tick if enough new speech; returns the summary or None."""
        now = now or time.time()
        window_start, self.last = self.last, now
        if self.store.count_since(window_start, "audio") < self.min_segments:
            return None
        minutes = (now - window_start) / 60
        return self.ai.summarize(minutes=minutes, max_images=self.max_images, save=True)

    def run(self) -> None:
        while not self.stop_ev.wait(self.every_min * 60):
            try:
                out = self.tick()
                if out:
                    log.info("auto-summary saved:\n%s", out)
            except Exception:
                log.exception("auto-summary failed (ANTHROPIC_API_KEY set?)")
