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
    return slug


@pytest.fixture()
def channel(ws):
    return make_channel(ws)
