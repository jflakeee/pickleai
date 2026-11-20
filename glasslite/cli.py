from __future__ import annotations

import argparse
import logging
import signal
import threading

from .config import Config
from .db import Store


def cmd_capture(cfg: Config, store: Store, args) -> None:
    from .capture import AudioCapturer, ScreenCapturer, find_loopback_device

    stop = threading.Event()
    signal.signal(signal.SIGINT, lambda *_: stop.set())
    threads: list[threading.Thread] = []
    if not args.no_screen:
        threads.append(ScreenCapturer(cfg, store, stop, monitor=args.monitor))
    if not args.no_audio:
        dev = args.device
        threads.append(AudioCapturer(cfg, store, stop, device=int(dev) if dev and dev.isdigit() else dev,
                                     label="me" if args.loopback else None))
    if args.loopback:
        idx = find_loopback_device()
        if idx is None:
            logging.warning("no loopback device found (install BlackHole / enable Stereo Mix); skipping system audio")
        else:
            logging.info("system audio from device #%d", idx)
            threads.append(AudioCapturer(cfg, store, stop, device=idx, label="them"))
    if args.summarize_every:
        from .autosummary import AutoSummarizer
        from .llm import Assistant

        threads.append(AutoSummarizer(Assistant(cfg, store), store, stop, args.summarize_every))
    removed = store.purge(cfg.retention_days)
    logging.info("capturing to %s (purged %d old segments). Ctrl+C to stop.", cfg.home, removed)
    for t in threads:
        t.start()
    while not stop.wait(1):
        pass


def main(argv: list[str] | None = None) -> None:
    p = argparse.ArgumentParser(prog="glasslite")
    sub = p.add_subparsers(dest="cmd", required=True)
    c = sub.add_parser("capture", help="run screen + audio capture")
    c.add_argument("--no-screen", action="store_true")
    c.add_argument("--no-audio", action="store_true")
    c.add_argument("--monitor", type=int, default=1, help="mss monitor index (1 = primary)")
    c.add_argument("--device", default=None, help="mic input device (index or name substring)")
    c.add_argument("--loopback", action="store_true",
                   help="also record system audio from an auto-detected loopback device")
    c.add_argument("--summarize-every", type=float, default=0, metavar="MIN",
                   help="auto-summarize via Claude API every MIN minutes (needs ANTHROPIC_API_KEY)")
    sub.add_parser("devices", help="list audio devices")
    sub.add_parser("mcp", help="run MCP server on stdio (for Claude Code)")
    s = sub.add_parser("summarize", help="summarize recent activity via Claude API")
    s.add_argument("--minutes", type=float, default=30)
    s.add_argument("--images", type=int, default=3)
    a = sub.add_parser("ask", help="ask about recent activity via Claude API")
    a.add_argument("question")
    a.add_argument("--minutes", type=float, default=60)
    r = sub.add_parser("recent", help="print recent timeline")
    r.add_argument("--minutes", type=float, default=30)
    args = p.parse_args(argv)

    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(threadName)s %(message)s")
    cfg = Config()
    cfg.ensure_dirs()

    if args.cmd == "mcp":
        from .mcp_server import build_server

        return build_server(cfg).run("stdio")
    if args.cmd == "devices":
        import sounddevice as sd

        from .capture import find_loopback_device

        print(sd.query_devices())
        idx = find_loopback_device()
        return print(f"\nloopback candidate: {'#' + str(idx) if idx is not None else 'none'}")

    store = Store(cfg.db_path)
    if args.cmd == "capture":
        cmd_capture(cfg, store, args)
    elif args.cmd == "recent":
        for seg in store.recent(args.minutes):
            print(seg.fmt())
    else:
        from .llm import Assistant

        ai = Assistant(cfg, store)
        print(ai.summarize(args.minutes, args.images) if args.cmd == "summarize" else ai.ask(args.question, args.minutes))


if __name__ == "__main__":
    main()
