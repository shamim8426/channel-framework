"""Provider registry. providers.<kind>.name in channel config picks the implementation:
    mock                      offline, free (default, and forced whenever --live is not given)
    gemini | cloudflare       live vendors (--live + key env var)
    "cloudflare,gemini"       FREE-FIRST chain: try in order, fall through on ProviderUnavailable (quota/overload)
    "package.module:Class"    your own provider class (constructor receives the provider conf dict)
"""
import importlib

from ..config import ChannelConfig
from .base import ImageProvider, LLMProvider, MusicProvider, ProviderUnavailable, Result, TTSProvider
from . import mock

KINDS = ("llm", "image", "tts", "music")
_MOCKS = {"llm": mock.MockLLM, "image": mock.MockImage, "tts": mock.MockTTS, "music": mock.MockMusic}


def _live_class(kind: str, name: str):
    if ":" in name:
        mod, cls = name.split(":", 1)
        return getattr(importlib.import_module(mod), cls)
    if name == "gemini":
        from . import gemini
        return {"llm": gemini.GeminiLLM, "image": gemini.GeminiImage, "tts": gemini.GeminiTTS}.get(kind)
    if name == "cloudflare" and kind == "image":
        from . import cloudflare
        return cloudflare.CloudflareImage
    return None


class Chain:
    """Free-first fallback chain over several providers of one kind."""

    def __init__(self, kind, providers):
        self.kind, self.providers, self.name = kind, providers, ",".join(p.name for p in providers)

    def __getattr__(self, attr):
        method = {"llm": "complete", "image": "generate", "tts": "synthesize", "music": "fetch"}[self.kind]
        if attr != method:
            raise AttributeError(attr)

        def call(*a, **kw):
            last = None
            for p in self.providers:
                try:
                    return getattr(p, method)(*a, **kw)
                except ProviderUnavailable as e:
                    last = e
            raise last or ProviderUnavailable(f"no {self.kind} provider available")
        return call


def get_provider(kind: str, cfg: ChannelConfig, live: bool = False):
    conf = cfg["providers"][kind]
    name = conf["name"]
    if not live or name == "mock":
        return _MOCKS[kind]()
    built = []
    for n in [x.strip() for x in name.split(",") if x.strip()]:
        cls = _live_class(kind, n)
        if cls is None:
            raise ValueError(f"providers.{kind}.name '{n}' is unknown (known: mock, gemini, cloudflare[image], package.module:Class)")
        built.append(cls(conf) if n != "mock" else _MOCKS[kind]())
    return built[0] if len(built) == 1 else Chain(kind, built)


def all_providers(cfg: ChannelConfig, live: bool = False) -> dict:
    return {k: get_provider(k, cfg, live) for k in KINDS}
