"""SQLite store with FTS5 full-text search over transcripts/summaries."""
from __future__ import annotations

import sqlite3
import time
from dataclasses import dataclass
from pathlib import Path

SCHEMA = """
CREATE TABLE IF NOT EXISTS segments (
    id INTEGER PRIMARY KEY,
    ts REAL NOT NULL,
    kind TEXT NOT NULL CHECK (kind IN ('audio', 'screen', 'summary')),
    text TEXT NOT NULL DEFAULT '',
    image_path TEXT
);
CREATE INDEX IF NOT EXISTS idx_segments_ts ON segments(ts);
CREATE VIRTUAL TABLE IF NOT EXISTS segments_fts USING fts5(
    text, content='segments', content_rowid='id', tokenize='trigram'
);
CREATE TRIGGER IF NOT EXISTS segments_ai AFTER INSERT ON segments BEGIN
    INSERT INTO segments_fts(rowid, text) VALUES (new.id, new.text);
END;
CREATE TRIGGER IF NOT EXISTS segments_ad AFTER DELETE ON segments BEGIN
    INSERT INTO segments_fts(segments_fts, rowid, text) VALUES ('delete', old.id, old.text);
END;
"""


@dataclass
class Segment:
    id: int
    ts: float
    kind: str
    text: str
    image_path: str | None

    def fmt(self) -> str:
        t = time.strftime("%Y-%m-%d %H:%M:%S", time.localtime(self.ts))
        body = self.text if self.kind != "screen" else f"[screenshot #{self.id}]"
        return f"[{t}] ({self.kind}) {body}"


class Store:
    def __init__(self, path: Path):
        path.parent.mkdir(parents=True, exist_ok=True)
        # check_same_thread=False: capture threads share one connection; writes are serialized by SQLite.
        self.conn = sqlite3.connect(path, check_same_thread=False, isolation_level=None)
        self.conn.execute("PRAGMA journal_mode=WAL")
        self.conn.executescript(SCHEMA)

    def add(self, kind: str, text: str = "", image_path: str | None = None, ts: float | None = None) -> int:
        cur = self.conn.execute(
            "INSERT INTO segments(ts, kind, text, image_path) VALUES (?, ?, ?, ?)",
            (ts or time.time(), kind, text, image_path),
        )
        return int(cur.lastrowid)

    def _rows(self, sql: str, args: tuple) -> list[Segment]:
        return [Segment(*r) for r in self.conn.execute(sql, args).fetchall()]

    def recent(self, minutes: float, kinds: tuple[str, ...] = ("audio", "screen", "summary")) -> list[Segment]:
        q = ",".join("?" * len(kinds))
        return self._rows(
            f"SELECT id, ts, kind, text, image_path FROM segments WHERE ts >= ? AND kind IN ({q}) ORDER BY ts",
            (time.time() - minutes * 60, *kinds),
        )

    def search(self, query: str, limit: int = 20) -> list[Segment]:
        # trigram tokenizer: works for Korean/CJK substrings; needs >= 3 chars.
        if len(query) < 3:
            return self._rows(
                "SELECT id, ts, kind, text, image_path FROM segments WHERE text LIKE ? ORDER BY ts DESC LIMIT ?",
                (f"%{query}%", limit),
            )
        phrase = '"' + query.replace('"', '""') + '"'
        return self._rows(
            "SELECT s.id, s.ts, s.kind, s.text, s.image_path FROM segments_fts f "
            "JOIN segments s ON s.id = f.rowid WHERE segments_fts MATCH ? ORDER BY s.ts DESC LIMIT ?",
            (phrase, limit),
        )

    def count_since(self, ts: float, kind: str) -> int:
        return self.conn.execute("SELECT COUNT(*) FROM segments WHERE ts >= ? AND kind = ?", (ts, kind)).fetchone()[0]

    def get(self, seg_id: int) -> Segment | None:
        rows = self._rows("SELECT id, ts, kind, text, image_path FROM segments WHERE id = ?", (seg_id,))
        return rows[0] if rows else None

    def latest_screen(self) -> Segment | None:
        rows = self._rows(
            "SELECT id, ts, kind, text, image_path FROM segments WHERE kind='screen' ORDER BY ts DESC LIMIT 1", ()
        )
        return rows[0] if rows else None

    def purge(self, older_than_days: int) -> int:
        cutoff = time.time() - older_than_days * 86400
        old = self._rows("SELECT id, ts, kind, text, image_path FROM segments WHERE ts < ?", (cutoff,))
        for s in old:
            if s.image_path:
                Path(s.image_path).unlink(missing_ok=True)
        self.conn.execute("DELETE FROM segments WHERE ts < ?", (cutoff,))
        return len(old)
