"""Provider interfaces. Pipelines only talk to these; real vendors and mocks are interchangeable (config: providers.<kind>.name).

    llm.complete(prompt, system="")            -> str
    image.generate(prompt, out_path, size=...) -> Result
    tts.synthesize(text, voice_id, out_path, style="") -> Result
    music.fetch(mood, out_path, seconds)       -> Result

Every call returns a cost in the channel budget currency (mock = 0). The runner writes it to the cost log."""
from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from pathlib import Path


class ProviderUnavailable(Exception):
    """Raised by a provider that cannot serve this call right now (quota, missing key). A fallback chain moves on."""


@dataclass
class Result:
    path: Path | None = None
    cost: float = 0.0
    provider: str = ""
    meta: dict = field(default_factory=dict)


class LLMProvider(ABC):
    name = "llm"

    @abstractmethod
    def complete(self, prompt: str, system: str = "") -> Result: ...


class ImageProvider(ABC):
    name = "image"

    @abstractmethod
    def generate(self, prompt: str, out_path: Path, size=(1280, 720)) -> Result: ...


class TTSProvider(ABC):
    name = "tts"

    @abstractmethod
    def synthesize(self, text: str, voice_id: str, out_path: Path, style: str = "") -> Result: ...


class MusicProvider(ABC):
    name = "music"

    @abstractmethod
    def fetch(self, mood: str, out_path: Path, seconds: float) -> Result: ...
