import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from core.paths import Workspace  # noqa: E402
from core.wizard import new_channel  # noqa: E402

BANNED = ["jugnu", "noor-e-raah", "noor e raah", "kissago", "dadi", "golu", "mitthu", "algieba", "sulafat", "quran", "hadith", "sahaba"]


@pytest.fixture()
def ws(tmp_path):
    (tmp_path / ".gitignore").write_text("secrets/\n")
    return Workspace(tmp_path)


def make_channel(ws, slug="demo-channel", pipeline="character_story", **kw):
    args = dict(slug=slug, name="Demo Channel", language="en", niche="demo niche stories", pipeline=pipeline,
                voices="v1,v2", visual_style="flat colour illustration, soft light", **kw)
    assert new_channel(ws, args, interactive=False) == 0
    import yaml  # keep mock runs small and fast
    f = ws.channel_dir(slug) / "channel.yaml"
    d = yaml.safe_load(f.read_text())
    d["formats"]["long"].update(min_seconds=5, max_seconds=300, script_words=[40, 300], max_images=3)
    if "shorts" in d["formats"]:
        d["formats"]["shorts"]["max_seconds"] = 12
    f.write_text(yaml.safe_dump(d, allow_unicode=True))
    return slug


@pytest.fixture()
def channel(ws):
    return make_channel(ws)
