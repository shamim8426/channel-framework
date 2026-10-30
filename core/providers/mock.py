"""Mock providers: deterministic, offline, free. Used by tests, the demo channel and every run without --live."""
import hashlib
import json
import math
import re
import struct
import wave
import zlib
from pathlib import Path

from .base import ImageProvider, LLMProvider, MusicProvider, Result, TTSProvider

WORDS = ("lantern river quiet morning small brave garden window story friend path stone bridge cloud kind seed "
         "wind lamp road open gentle night bright slow warm hill field map note song").split()


def _hdr(prompt: str) -> dict:
    """Header lines of a task prompt: 'TASK: x', 'WORDS: a-b', 'SPEAKERS: a,b', 'FACTS: F1,F2', 'AYAT: 1,2'."""
    out = {}
    for line in prompt.splitlines()[:12]:
        m = re.match(r"^([A-Z_]+):\s*(.*)$", line.strip())
        if m:
            out[m.group(1)] = m.group(2)
    return out


def _sentence(seed: int, n=8) -> str:
    return " ".join(WORDS[(seed * 7 + i * 3) % len(WORDS)] for i in range(n)).capitalize() + "."


class MockLLM(LLMProvider):
    name = "mock"

    def complete(self, prompt: str, system: str = "") -> Result:
        h = _hdr(prompt)
        task = h.get("TASK", "text")
        idea = h.get("IDEA", "an idea")
        if task == "research":
            facts = [{"id": f"F{i}", "claim": f"Mock fact {i} about {idea}.",
                      "sources": [{"title": "Mock Source A", "ref": f"A:{i}"}, {"title": "Mock Source B", "ref": f"B:{i}"}]}
                     for i in range(1, 5)]
            text = json.dumps({"topic": idea, "facts": facts})
        elif task == "script_character":
            lo, hi = (int(x) for x in h.get("WORDS", "60-400").split("-"))
            speakers = [s for s in h.get("SPEAKERS", "narrator").split(",") if s]
            target, lines, n, words = (lo + hi) // 2, [], 0, 0
            while words < target:
                n += 1
                t = _sentence(n, 9)
                lines.append({"n": n, "speaker": speakers[(n - 1) % len(speakers)], "text": t, "scene": (n - 1) // 3 + 1})
                words += len(t.split())
            scenes = [{"id": s, "prompt": f"scene {s}: " + _sentence(s, 6)} for s in sorted({l["scene"] for l in lines})]
            lines[0]["text"] = "Hook: " + lines[0]["text"]
            text = json.dumps({"title": idea.title(), "hook": lines[0]["text"], "lines": lines, "scenes": scenes})
        elif task == "script_surah":
            speakers = [s for s in h.get("SPEAKERS", "ustaad").split(",") if s]
            facts = [f for f in h.get("FACTS", "").split(",") if f]
            lines = [{"n": 1, "speaker": speakers[0], "text": f"Today we read {idea}.", "scene": 1, "tags": []}]
            for i, f in enumerate(facts, 2):
                lines.append({"n": i, "speaker": speakers[(i - 1) % len(speakers)], "text": _sentence(i, 9), "scene": 1 + i // 3,
                              "tags": [f]})
            scenes = [{"id": s, "prompt": f"scene {s}: " + _sentence(s, 6)} for s in sorted({l["scene"] for l in lines})]
            text = json.dumps({"title": idea.title(), "hook": lines[0]["text"], "lines": lines, "scenes": scenes})
        elif task == "short_script":
            text = json.dumps({"title": idea.title() + " (short)", "text": _sentence(3, 12)})
        else:
            text = "PASS"
        return Result(provider="mock", cost=0.0, meta={"task": task, "text": text})


def write_png(path: Path, rgb, size=(1280, 720), label_seed=0):
    """Tiny valid PNG (solid colour + a few stripes) without needing Pillow."""
    w, h = size
    row0 = b"\x00" + bytes(rgb) * w
    stripe = b"\x00" + bytes(min(255, c + 40) for c in rgb) * w
    raw = b"".join(stripe if (y // 40 + label_seed) % 7 == 0 else row0 for y in range(h))

    def chunk(t, d):
        c = struct.pack(">I", len(d)) + t + d
        return c + struct.pack(">I", zlib.crc32(t + d) & 0xFFFFFFFF)

    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(b"\x89PNG\r\n\x1a\n" + chunk(b"IHDR", struct.pack(">IIBBBBB", w, h, 8, 2, 0, 0, 0)) +
                     chunk(b"IDAT", zlib.compress(raw, 1)) + chunk(b"IEND", b""))


class MockImage(ImageProvider):
    name = "mock"

    def generate(self, prompt, out_path, size=(1280, 720)):
        d = hashlib.sha256(prompt.encode()).digest()
        write_png(Path(out_path), (40 + d[0] % 120, 40 + d[1] % 120, 40 + d[2] % 120), size, d[3] % 7)
        return Result(Path(out_path), 0.0, "mock", {"prompt": prompt})


def write_wav(path: Path, seconds: float, freq=0.0, sr=24000):
    import numpy as np
    path.parent.mkdir(parents=True, exist_ok=True)
    n = int(seconds * sr)
    t = np.arange(n) / sr
    pcm = (2000 * np.sin(2 * np.pi * freq * t)).astype("<i2") if freq else np.zeros(n, "<i2")
    with wave.open(str(path), "wb") as w:
        w.setnchannels(1), w.setsampwidth(2), w.setframerate(sr)
        w.writeframes(pcm.tobytes())


class MockTTS(TTSProvider):
    name = "mock"

    def synthesize(self, text, voice_id, out_path, style=""):
        secs = max(0.5, 0.35 * len(text.split()))  # ~170 wpm
        write_wav(Path(out_path), secs, freq=180 + (hashlib.sha256(voice_id.encode()).digest()[0] % 120))
        return Result(Path(out_path), 0.0, "mock", {"seconds": secs, "voice_id": voice_id})


class MockMusic(MusicProvider):
    name = "mock"

    def fetch(self, mood, out_path, seconds):
        write_wav(Path(out_path), min(seconds, 20.0), freq=110)
        return Result(Path(out_path), 0.0, "mock", {"mood": mood})
