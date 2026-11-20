"""Append every captured segment to a daily Markdown file, so Claude Code (or a human)
can Grep/Read the memory without any server."""
from __future__ import annotations

import threading
import time
from pathlib import Path

from .db import Segment


class MarkdownExporter:
    def __init__(self, notes_dir: Path):
        self.dir = notes_dir
        self.dir.mkdir(parents=True, exist_ok=True)
        self._lock = threading.Lock()

    def path_for(self, ts: float) -> Path:
        return self.dir / time.strftime("%Y-%m-%d.md", time.localtime(ts))

    def __call__(self, seg: Segment) -> None:
        t = time.strftime("%H:%M:%S", time.localtime(seg.ts))
        if seg.kind == "screen":
            line = f"- {t} 🖥 screenshot #{seg.id}: `{seg.image_path}`"
        elif seg.kind == "summary":
            line = f"\n### {t} summary #{seg.id}\n\n{seg.text}\n"
        else:
            line = f"- {t} {seg.text}"
        path = self.path_for(seg.ts)
        with self._lock:
            new = not path.exists()
            with path.open("a", encoding="utf-8") as f:
                if new:
                    f.write(f"# {path.stem}\n\n")
                f.write(line + "\n")
