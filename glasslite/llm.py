"""Optional: standalone summarize/ask via the Claude API (Claude Code via MCP doesn't need this)."""
from __future__ import annotations

import base64
from pathlib import Path

import anthropic

from .config import Config
from .db import Segment, Store

SYSTEM = (
    "You are a personal meeting/work-context assistant. You get timestamped speech transcripts "
    "(Whisper output, may contain recognition errors) and screenshots of the user's screen. "
    "Answer in the user's language. Be concise; use bullet points for summaries. "
    "If the context does not contain the answer, say so instead of guessing."
)


def _image_block(path: str) -> dict:
    data = base64.standard_b64encode(Path(path).read_bytes()).decode()
    return {"type": "image", "source": {"type": "base64", "media_type": "image/jpeg", "data": data}}


def build_content(segs: list[Segment], max_images: int) -> list[dict]:
    transcript = "\n".join(s.fmt() for s in segs if s.kind != "screen") or "(no transcript)"
    shots = [s for s in segs if s.kind == "screen" and s.image_path and Path(s.image_path).exists()]
    content: list[dict] = []
    for s in shots[-max_images:] if max_images else []:
        content.append({"type": "text", "text": s.fmt()})
        content.append(_image_block(s.image_path))
    content.append({"type": "text", "text": f"<transcript>\n{transcript}\n</transcript>"})
    return content


class Assistant:
    def __init__(self, cfg: Config, store: Store, client: anthropic.Anthropic | None = None):
        self.cfg, self.store = cfg, store
        self.client = client or anthropic.Anthropic()

    def _call(self, content: list[dict]) -> str:
        resp = self.client.beta.messages.create(
            model=self.cfg.claude_model,
            max_tokens=16000,
            system=SYSTEM,
            output_config={"effort": "medium"},
            # Server-side refusal fallback (routes declined requests to a fallback model automatically).
            betas=["server-side-fallback-2026-07-01"],
            fallbacks="default",
            messages=[{"role": "user", "content": content}],
        )
        if resp.stop_reason == "refusal":
            cat = resp.stop_details.category if resp.stop_details else None
            return f"[refused: {cat}]"
        return "".join(b.text for b in resp.content if b.type == "text").strip()

    def summarize(self, minutes: float = 30, max_images: int = 3, save: bool = True) -> str:
        segs = self.store.recent(minutes, kinds=("audio", "screen"))
        if not segs:
            return "(no captured data in that window)"
        content = build_content(segs, max_images)
        content.append({"type": "text", "text": "Summarize: key topics, decisions, action items (owner/due if stated)."})
        out = self._call(content)
        if save and not out.startswith("[refused"):
            self.store.add("summary", text=out)
        return out

    def ask(self, question: str, minutes: float = 60, max_images: int = 2) -> str:
        segs = self.store.recent(minutes)
        content = build_content(segs, max_images)
        content.append({"type": "text", "text": f"Question: {question}"})
        return self._call(content)
