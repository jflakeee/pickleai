"""MCP server: lets Claude Code query the captured memory. No Anthropic API key needed —
Claude Code itself does the reasoning over what these tools return."""
from __future__ import annotations

from mcp.server.mcpserver import Image, MCPServer

from .config import Config
from .db import Store


def build_server(cfg: Config | None = None, store: Store | None = None) -> MCPServer:
    cfg = cfg or Config()
    store = store or Store(cfg.db_path)
    mcp = MCPServer(
        name="glasslite",
        instructions=(
            "Local memory of the user's screen and speech (Whisper transcripts, may contain errors). "
            "Use recent_activity for 'what just happened', search_memory for keywords, "
            "get_screenshot to look at a captured screen."
        ),
    )

    @mcp.tool()
    def recent_activity(minutes: float = 30, include_screens: bool = True) -> str:
        """Timeline of transcripts, screenshots (ids only) and saved summaries from the last N minutes."""
        kinds = ("audio", "screen", "summary") if include_screens else ("audio", "summary")
        segs = store.recent(minutes, kinds)
        return "\n".join(s.fmt() for s in segs) or f"(nothing captured in the last {minutes} min)"

    @mcp.tool()
    def search_memory(query: str, limit: int = 20) -> str:
        """Full-text search over transcripts and summaries (substring match, Korean OK). Newest first."""
        segs = store.search(query, limit)
        return "\n".join(f"#{s.id} {s.fmt()}" for s in segs) or "(no matches)"

    @mcp.tool()
    def get_screenshot(segment_id: int | None = None) -> Image | str:
        """Return a captured screenshot image. Omit segment_id for the most recent one."""
        seg = store.get(segment_id) if segment_id is not None else store.latest_screen()
        if not seg or seg.kind != "screen" or not seg.image_path:
            return "(screenshot not found)"
        return Image(path=seg.image_path)

    @mcp.tool()
    def save_note(text: str) -> str:
        """Store a summary/note (e.g. a meeting summary Claude wrote) so it becomes searchable later."""
        return f"saved #{store.add('summary', text=text)}"

    return mcp


def main() -> None:
    build_server().run("stdio")


if __name__ == "__main__":
    main()
