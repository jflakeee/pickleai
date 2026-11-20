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


class AudioCapturer(threading.Thread):
    """Mic (or loopback device) -> fixed-size chunks -> faster-whisper -> Store.

    System audio (the other side of a call) needs a loopback device:
    macOS: BlackHole / Windows: WASAPI loopback / Linux: PulseAudio monitor source.
    Pick it with GLASSLITE_AUDIO_DEVICE (name substring or index; `glasslite devices` lists them).
    """

    SR = 16_000

    def __init__(self, cfg: Config, store: Store, stop: threading.Event, device: str | int | None = None):
        super().__init__(daemon=True, name="audio")
        self.cfg, self.store, self.stop_ev, self.device = cfg, store, stop, device
        self.q: queue.Queue[np.ndarray] = queue.Queue()
        self._model = None

    def model(self):
        if self._model is None:
            from faster_whisper import WhisperModel

            self._model = WhisperModel(self.cfg.whisper_model, device="auto", compute_type="int8")
        return self._model

    def transcribe(self, audio: np.ndarray) -> str:
        segments, _ = self.model().transcribe(
            audio, language=self.cfg.whisper_language, vad_filter=True, beam_size=1
        )
        return " ".join(s.text.strip() for s in segments).strip()

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
                    sid = self.store.add("audio", text=text, ts=start)
                    log.info("audio #%d: %s", sid, text[:80])
