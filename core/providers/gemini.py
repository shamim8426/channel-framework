"""Live Google Gemini providers (REST via requests). NOT exercised by the test-suite (no paid calls while building): they run only
with --live and a key in the env var named by providers.<kind>.api_key_env. Model names come from config (model:), never hardcoded."""
import base64
import wave
from pathlib import Path

import requests

from ..secrets import api_key
from .base import ImageProvider, LLMProvider, ProviderUnavailable, Result, TTSProvider

BASE = "https://generativelanguage.googleapis.com/v1beta/models"


def _call(model: str, key: str, body: dict, timeout=180) -> dict:
    r = requests.post(f"{BASE}/{model}:generateContent", params={"key": key}, json=body, timeout=timeout)
    if r.status_code in (429, 503):
        raise ProviderUnavailable(f"gemini {r.status_code}: quota or overload")
    if r.status_code != 200:
        raise RuntimeError(f"gemini {r.status_code}: {r.text[:300]}")
    return r.json()


def _parts(resp: dict) -> list:
    return resp["candidates"][0]["content"]["parts"]


class GeminiLLM(LLMProvider):
    name = "gemini"

    def __init__(self, conf: dict):
        self.model, self.env = conf.get("model", ""), conf.get("api_key_env")

    def complete(self, prompt, system=""):
        body = {"contents": [{"parts": [{"text": prompt}]}]}
        if system:
            body["systemInstruction"] = {"parts": [{"text": system}]}
        text = "".join(p.get("text", "") for p in _parts(_call(self.model, api_key(self.env), body)))
        return Result(provider=self.name, cost=0.0, meta={"text": text})  # token cost: add your pricing hook here


class GeminiImage(ImageProvider):
    name = "gemini"

    def __init__(self, conf: dict):
        self.model, self.env = conf.get("model", ""), conf.get("api_key_env")

    def generate(self, prompt, out_path, size=(1280, 720)):
        ratio = {(1280, 720): "16:9", (720, 1280): "9:16", (1080, 1080): "1:1"}.get(tuple(size))
        gen = {"responseModalities": ["IMAGE"]}
        if ratio:
            gen["imageConfig"] = {"aspectRatio": ratio}
        body = {"contents": [{"parts": [{"text": prompt}]}], "generationConfig": gen}
        for p in _parts(_call(self.model, api_key(self.env), body)):
            if "inlineData" in p:
                Path(out_path).parent.mkdir(parents=True, exist_ok=True)
                Path(out_path).write_bytes(base64.b64decode(p["inlineData"]["data"]))
                return Result(Path(out_path), 0.0, self.name)
        raise RuntimeError("gemini returned no image")


class GeminiTTS(TTSProvider):
    name = "gemini"

    def __init__(self, conf: dict):
        self.model, self.env = conf.get("model", ""), conf.get("api_key_env")

    def synthesize(self, text, voice_id, out_path, style=""):
        body = {"contents": [{"parts": [{"text": (style + ": " if style else "") + text}]}],
                "generationConfig": {"responseModalities": ["AUDIO"], "speechConfig": {
                    "voiceConfig": {"prebuiltVoiceConfig": {"voiceName": voice_id}}}}}
        for p in _parts(_call(self.model, api_key(self.env), body)):
            if "inlineData" in p:
                pcm = base64.b64decode(p["inlineData"]["data"])  # 16-bit mono PCM, 24 kHz
                Path(out_path).parent.mkdir(parents=True, exist_ok=True)
                with wave.open(str(out_path), "wb") as w:
                    w.setnchannels(1), w.setsampwidth(2), w.setframerate(24000)
                    w.writeframes(pcm)
                return Result(Path(out_path), 0.0, self.name, {"seconds": len(pcm) / 48000})
        raise RuntimeError("gemini returned no audio")
