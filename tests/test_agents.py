import re

import pytest

from core.agents import ROLES, render_agents, render_template, context_for
from core.config import load_channel
from core.errors import FrameworkError
from tests.conftest import make_channel


def test_render_all_roles_no_unresolved(ws, channel):
    cfg = load_channel(channel, ws)
    files = render_agents(cfg, ws)
    assert {f.name for f in files} == {f"{r}-{channel}.md" for r in ROLES}
    for f in files:
        t = f.read_text()
        assert not re.search(r"\{\{|\}\}", t), f
        assert "Demo Channel" in t and t.startswith("---\nname:")


def test_real_sourced_blocks_only_for_real_sourced(ws):
    make_channel(ws, "fic-chan")
    make_channel(ws, "real-chan", pipeline="surah_explainer")
    fic = render_agents(load_channel("fic-chan", ws), ws)
    real = render_agents(load_channel("real-chan", ws), ws)
    k = lambda fs, r: next(f for f in fs if f.name.startswith(r)).read_text()
    assert "MANDATORY" not in k(fic, "khoji") and "MANDATORY" in k(real, "khoji")
    assert "Source check is MANDATORY" in k(real, "munshi") and "Source check is MANDATORY" not in k(fic, "munshi")


def test_unknown_variable_is_an_error():
    with pytest.raises(FrameworkError, match="unknown variable"):
        render_template("hello {{ channel.nope }}", {"channel": {"name": "x"}})
