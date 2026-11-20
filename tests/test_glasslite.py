import os
import sys
from pathlib import Path
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
    pytest.importorskip("mcp")
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


def test_find_loopback_device():
    from glasslite.capture import find_loopback_device

    devs = [
        {"name": "MacBook Pro Microphone", "max_input_channels": 1},
        {"name": "BlackHole 2ch", "max_input_channels": 0},  # output side: ignored
        {"name": "BlackHole 2ch", "max_input_channels": 2},
    ]
    assert find_loopback_device(devs) == 2
    assert find_loopback_device([{"name": "스테레오 믹스(Realtek)", "max_input_channels": 2}]) == 0
    assert find_loopback_device([{"name": "USB Mic", "max_input_channels": 1}]) is None


def test_audio_label_prefix(env, monkeypatch):
    import threading

    import numpy as np

    from glasslite.capture import AudioCapturer

    cfg, store = env
    cap = AudioCapturer(cfg, store, threading.Event(), label="them")
    monkeypatch.setattr(cap, "transcribe", lambda a: "견적 다시 보내주세요")
    fake_sd = SimpleNamespace(InputStream=None)

    class Stream:
        def __init__(self, callback, **kw):
            self.cb = callback

        def __enter__(self):
            # feed exactly one chunk, then stop
            self.cb(np.zeros((int(cap.SR * cfg.audio_chunk), 1), dtype="float32"), 0, None, None)
            threading.Timer(0.3, cap.stop_ev.set).start()

        def __exit__(self, *a):
            pass

    fake_sd.InputStream = Stream
    monkeypatch.setitem(sys.modules, "sounddevice", fake_sd)
    cap.run()
    assert store.search("견적 다시")[0].text == "[them] 견적 다시 보내주세요"


def test_autosummarizer_tick(env):
    from glasslite.autosummary import AutoSummarizer

    _, store = env
    calls = []
    ai = SimpleNamespace(summarize=lambda **kw: calls.append(kw) or "- 요약")
    auto = AutoSummarizer(ai, store, stop=None, every_min=10, min_segments=2)
    auto.last -= 600
    store.add("audio", "하나")
    assert auto.tick() is None and not calls  # not enough new speech
    auto.last -= 600
    store.add("audio", "둘")
    store.add("audio", "셋")
    assert auto.tick() == "- 요약"
    assert 9 < calls[0]["minutes"] < 11 and calls[0]["save"] is True


def test_cli_query_commands(env, capsys):
    from glasslite.cli import main

    cfg, store = env
    store.add("audio", "[them] 계약서는 금요일까지 회신")
    sid = ScreenCapturer(cfg, store, stop=None).process(Image.new("RGB", (640, 480), "green"))

    main(["search", "계약서"])
    assert "금요일" in capsys.readouterr().out
    main(["recent", "--minutes", "5"])
    assert f"[screenshot #{sid}]" in capsys.readouterr().out
    main(["shot"])
    path = capsys.readouterr().out.strip()
    assert path == store.get(sid).image_path and Path(path).exists()
    main(["note", "회의 요약: 계약서 금요일 회신"])
    assert capsys.readouterr().out.startswith("saved #")
    main(["search", "회의 요약"])
    assert "(summary)" in capsys.readouterr().out
    with pytest.raises(SystemExit):
        main(["shot", "99999"])


def test_markdown_export(env):
    from glasslite.export import MarkdownExporter

    cfg, store = env
    exp = MarkdownExporter(cfg.notes_dir)
    store.listeners.append(exp)
    store.add("audio", "[me] 배포는 다음 주")
    store.add("summary", "- 배포 다음 주")
    files = list(cfg.notes_dir.glob("*.md"))
    assert len(files) == 1
    text = files[0].read_text(encoding="utf-8")
    assert text.startswith("# ") and "[me] 배포는 다음 주" in text and "summary #2" in text


def test_install_skill(tmp_path):
    import json

    from glasslite.install import RULE, install_skill

    home = tmp_path / ".claude"
    home.mkdir()
    (home / "settings.json").write_text(json.dumps({"permissions": {"allow": ["Bash(ls *)"]}, "theme": "dark"}))
    install_skill(home, allow=True)
    install_skill(home, allow=True)  # idempotent
    skill = (home / "skills/glasslite/SKILL.md").read_text(encoding="utf-8")
    assert skill.startswith("---\nname: glasslite")
    settings = json.loads((home / "settings.json").read_text())
    assert settings["permissions"]["allow"] == ["Bash(ls *)", RULE] and settings["theme"] == "dark"
