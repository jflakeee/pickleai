import os
import sys
from types import SimpleNamespace

import anyio
import pytest
from PIL import Image

from glasslite.capture import ScreenCapturer
from glasslite.config import Config
from glasslite.db import Store
from glasslite.llm import Assistant


@pytest.fixture
def env(tmp_path, monkeypatch):
    monkeypatch.setenv("GLASSLITE_HOME", str(tmp_path))
    cfg = Config(home=tmp_path)
    cfg.ensure_dirs()
    return cfg, Store(cfg.db_path)


def test_search_korean_and_short(env):
    _, store = env
    store.add("audio", "다음 주 화요일까지 견적서 보내기로 했습니다")
    store.add("audio", "budget review meeting")
    assert len(store.search("견적서")) == 1
    assert len(store.search("화요")) == 1  # <3 chars -> LIKE fallback
    assert store.search("없는단어") == []


def test_screen_dedupe(env):
    cfg, store = env
    cap = ScreenCapturer(cfg, store, stop=None)
    white = Image.new("RGB", (3000, 1600), "white")
    assert cap.process(white) is not None
    assert cap.process(white.copy()) is None  # identical frame skipped
    black = Image.new("RGB", (3000, 1600), "black")
    sid = cap.process(black)
    seg = store.get(sid)
    assert Image.open(seg.image_path).width == cfg.screen_max_width


def test_assistant_payload(env):
    cfg, store = env
    ScreenCapturer(cfg, store, stop=None).process(Image.new("RGB", (800, 600), "red"))
    store.add("audio", "출시일은 12월 3일로 확정")
    seen = {}

    def create(**kw):
        seen.update(kw)
        return SimpleNamespace(stop_reason="end_turn", stop_details=None,
                               content=[SimpleNamespace(type="text", text="- 출시일 12/3 확정")])

    fake = SimpleNamespace(beta=SimpleNamespace(messages=SimpleNamespace(create=create)))
    out = Assistant(cfg, store, client=fake).summarize(minutes=5)
    assert out == "- 출시일 12/3 확정"
    content = seen["messages"][0]["content"]
    assert any(b["type"] == "image" for b in content)
    assert "출시일" in content[-2]["text"]
    assert seen["model"] == "claude-opus-5-5" and seen["fallbacks"] == "default"
    assert store.search("출시일 12")  # summary saved + searchable


def test_mcp_stdio_end_to_end(env):
    from mcp import Client, StdioServerParameters

    cfg, store = env
    store.add("audio", "회의록: 서버 이전은 1월에 진행")
    ScreenCapturer(cfg, store, stop=None).process(Image.new("RGB", (640, 480), "blue"))
    params = StdioServerParameters(command=sys.executable, args=["-m", "glasslite.cli", "mcp"],
                                   env={**os.environ, "GLASSLITE_HOME": str(cfg.home)})

    async def run():
        async with Client(params) as c:
            names = {t.name for t in (await c.list_tools()).tools}
            assert {"recent_activity", "search_memory", "get_screenshot", "save_note"} <= names
            r = await c.call_tool("search_memory", {"query": "서버 이전"})
            assert "1월" in r.content[0].text
            r = await c.call_tool("get_screenshot", {})
            assert r.content[0].type == "image" and r.content[0].mime_type == "image/jpeg"
            r = await c.call_tool("recent_activity", {"minutes": 5})
            assert "screenshot #" in r.content[0].text

    anyio.run(run)
