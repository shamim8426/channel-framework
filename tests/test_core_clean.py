"""core/ and agents/ must not contain channel names, characters, voice IDs or style prompts."""
from pathlib import Path

from tests.conftest import BANNED

ROOT = Path(__file__).resolve().parent.parent


def test_no_channel_specific_strings_in_engine():
    hits = []
    for base in ("core", "agents"):
        for f in (ROOT / base).rglob("*"):
            if f.is_file() and f.suffix in (".py", ".json", ".tmpl", ".md") and "__pycache__" not in f.parts:
                low = f.read_text(encoding="utf-8").lower()
                hits += [f"{f.relative_to(ROOT)}: {b}" for b in BANNED if b in low]
    assert not hits, hits


def test_no_secret_shaped_files_in_repo():
    for f in ROOT.rglob("*"):
        if ".git" in f.parts or not f.is_file():
            continue
        assert f.name not in ("client_secret.json", "token.json", ".env"), f
