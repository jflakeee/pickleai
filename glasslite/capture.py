"""Screen + microphone capture loops. Each runs in its own thread and writes to Store."""
from __future__ import annotations

import io
import logging
import queue
import threading
import time
from pathlib import Path

import numpy as np
from PIL import Image

from .config import Config
from .db import Store

log = logging.getLogger(__name__)


def changed_fraction(a: Image.Image, b: Image.Image, size=(96, 54), tol: int = 12) -> float:
    """Fraction of pixels that differ noticeably between two frames (cheap dedupe)."""
    x = np.asarray(a.convert("L").resize(size), dtype=np.int16)
    y = np.asarray(b.convert("L").resize(size), dtype=np.int16)
    return float((np.abs(x - y) > tol).mean())


def downscale(img: Image.Image, max_width: int) -> Image.Image:
    if img.width <= max_width:
        return img
    h = round(img.height * max_width / img.width)
    return img.resize((max_width, h), Image.LANCZOS)


class ScreenCapturer(threading.Thread):
    def __init__(self, cfg: Config, store: Store, stop: threading.Event, monitor: int = 1):
        super().__init__(daemon=True, name="screen")
        self.cfg, self.store, self.stop_ev, self.monitor = cfg, store, stop, monitor
        self._prev: Image.Image | None = None

    def grab(self) -> Image.Image:
        import mss  # lazy: needs a display

        with mss.mss() as sct:
            raw = sct.grab(sct.monitors[self.monitor])
            return Image.frombytes("RGB", raw.size, raw.rgb)

    def process(self, img: Image.Image) -> int | None:
        """Save frame if it differs enough from the previous one. Returns segment id or None."""
        img = downscale(img, self.cfg.screen_max_width)
        if self._prev is not None and changed_fraction(self._prev, img) < self.cfg.screen_diff_threshold:
            return None
        self._prev = img
        ts = time.time()
        path = self.cfg.shots_dir / time.strftime("%Y%m%d-%H%M%S.jpg", time.localtime(ts))
        img.save(path, "JPEG", quality=80)
        return self.store.add("screen", image_path=str(path), ts=ts)

    def run(self) -> None:
        while not self.stop_ev.is_set():
            try:
                sid = self.process(self.grab())
                if sid:
                    log.info("screen #%d saved", sid)
            except Exception:
                log.exception("screen capture failed")
            self.stop_ev.wait(self.cfg.screen_interval)


# Input devices that carry system audio (the other side of a call), by platform.
LOOPBACK_HINTS = (
    "blackhole", "soundflower", "loopback",                # macOS
    "stereo mix", "스테레오 믹스", "what u hear", "cable output", "vb-audio",  # Windows
    "monitor of", ".monitor",                              # Linux PulseAudio/PipeWire
)


def find_loopback_device(devices: list[dict] | None = None) -> int | None:
    """Index of the first input device that looks like a system-audio loopback, else None."""
    if devices is None:
        import sounddevice as sd

        devices = list(sd.query_devices())
    for i, d in enumerate(devices):
        name = str(d.get("name", "")).lower()
        if d.get("max_input_channels", 0) > 0 and any(h in name for h in LOOPBACK_HINTS):
            return i
    return None


class _Whisper:
    """One faster-whisper model shared by all audio threads (loaded once, calls serialized)."""

    _model = None
    _lock = threading.Lock()

    @classmethod
    def transcribe(cls, cfg: Config, audio: np.ndarray) -> str:
        with cls._lock:
            if cls._model is None:
                from faster_whisper import WhisperModel

                cls._model = WhisperModel(cfg.whisper_model, device="auto", compute_type="int8")
            segments, _ = cls._model.transcribe(
                audio, language=cfg.whisper_language, vad_filter=True, beam_size=1
            )
            return " ".join(s.text.strip() for s in segments).strip()


class AudioCapturer(threading.Thread):
    """Audio input device -> fixed-size chunks -> faster-whisper -> Store.

    Run one for the mic (label "me") and one for a loopback device (label "them")
    to capture both sides of a call. `glasslite devices` lists devices.
    """

    SR = 16_000

    def __init__(self, cfg: Config, store: Store, stop: threading.Event,
                 device: str | int | None = None, label: str | None = None):
        super().__init__(daemon=True, name=f"audio-{label or 'mic'}")
        self.cfg, self.store, self.stop_ev, self.device, self.label = cfg, store, stop, device, label
        self.q: queue.Queue[np.ndarray] = queue.Queue()

    def transcribe(self, audio: np.ndarray) -> str:
        return _Whisper.transcribe(self.cfg, audio)

    def run(self) -> None:
        import sounddevice as sd

        def cb(indata, frames, t, status):
            if status:
                log.warning("audio: %s", status)
            self.q.put(indata[:, 0].copy())

        need = int(self.SR * self.cfg.audio_chunk)
        buf: list[np.ndarray] = []
        n = 0
        with sd.InputStream(samplerate=self.SR, channels=1, dtype="float32", device=self.device, callback=cb):
            while not self.stop_ev.is_set():
                try:
                    block = self.q.get(timeout=0.5)
                except queue.Empty:
                    continue
                buf.append(block)
                n += len(block)
                if n < need:
                    continue
                audio, buf, n = np.concatenate(buf), [], 0
                start = time.time() - len(audio) / self.SR
                try:
                    text = self.transcribe(audio)
                except Exception:
                    log.exception("transcription failed")
                    continue
                if text:
                    if self.label:
                        text = f"[{self.label}] {text}"
                    sid = self.store.add("audio", text=text, ts=start)
                    log.info("audio #%d: %s", sid, text[:80])
