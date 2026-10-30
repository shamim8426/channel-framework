import datetime as dt
import subprocess

import pytest

from core import youtube
from core.config import load_channel
from core.costlog import CostLog
from core.errors import BudgetError, GuardError, SecretsError
from core.secrets import SecretStore, api_key, gitignore_protects_secrets
from tests.conftest import make_channel

REAL_ID = "UC" + "a" * 22
OTHER_ID = "UC" + "b" * 22


def cfg_with_id(ws, channel, cid=REAL_ID):
    import yaml
    f = ws.channel_dir(channel) / "channel.yaml"
    d = yaml.safe_load(f.read_text())
    d["youtube_channel_id"] = cid
    f.write_text(yaml.safe_dump(d))
    return load_channel(channel, ws)


def job(cfg, tmp_path):
    v = tmp_path / "v.mp4"
    v.write_bytes(b"x")
    return youtube.build_job(cfg, v, "long", "My title", "desc")


def test_guard_aborts_on_mismatch_and_uploads_nothing(ws, channel, tmp_path):
    cfg = cfg_with_id(ws, channel)
    fake = youtube.FakeYouTube(OTHER_ID)
    with pytest.raises(GuardError, match="WRONG CHANNEL"):
        youtube.upload(cfg, fake, job(cfg, tmp_path), live=True)
    assert fake.uploads == []


def test_guard_passes_on_match(ws, channel, tmp_path):
    cfg = cfg_with_id(ws, channel)
    fake = youtube.FakeYouTube(REAL_ID)
    res = youtube.upload(cfg, fake, job(cfg, tmp_path), live=True)
    assert len(fake.uploads) == 1 and res["privacy"] == "private"


def test_live_refuses_placeholder_channel_id(ws, channel, tmp_path):
    cfg = load_channel(channel, ws)
    with pytest.raises(GuardError, match="REPLACE_ME"):
        youtube.upload(cfg, youtube.FakeYouTube(REAL_ID), job(cfg, tmp_path), live=True)


def test_job_body_comes_from_config(ws, channel, tmp_path):
    cfg = load_channel(channel, ws)
    b = job(cfg, tmp_path)["body"]
    assert b["snippet"]["categoryId"] == "22" and b["status"]["selfDeclaredMadeForKids"] is False
    assert b["snippet"]["title"].endswith("| Demo Channel") and b["status"]["privacyStatus"] == "private"


def test_secret_store_paths_and_messages(ws, channel):
    st = SecretStore(ws, "my-ref")
    assert st.path("token") == ws.root / "secrets" / "my-ref" / "token.json"
    with pytest.raises(SecretsError, match="gitignored"):
        st.require("token")
    st.ensure_dir()
    st.path("token").write_text("{}")
    assert st.has("token") and st.status()["client_secret"] is False
    with pytest.raises(SecretsError):
        st.path("nonsense")


def test_api_key_comes_from_env_only(monkeypatch):
    monkeypatch.delenv("SOME_KEY", raising=False)
    with pytest.raises(SecretsError, match="SOME_KEY"):
        api_key("SOME_KEY")
    monkeypatch.setenv("SOME_KEY", "abc")
    assert api_key("SOME_KEY") == "abc"


def test_gitignore_protects_secrets(tmp_path):
    assert not gitignore_protects_secrets(tmp_path)
    (tmp_path / ".gitignore").write_text("secrets/\n")
    assert gitignore_protects_secrets(tmp_path)


def test_repo_gitignore_covers_secrets_and_media():
    import pathlib
    gi = (pathlib.Path(__file__).resolve().parent.parent / ".gitignore").read_text()
    for pat in ("secrets/", "*.mp4", "*.wav", "token.json", "client_secret*.json"):
        assert pat in gi


def test_costlog_and_budget_cap(ws, channel):
    cfg = load_channel(channel, ws)
    log = CostLog(ws, cfg)
    log.append("p1", "mock", "image", 50.0)
    log.append("p1", "mock", "tts", 60.0)
    log.append("p2", "mock", "tts", 5.0)
    assert log.total("p1") == 110.0 and log.total() == 115.0
    log.check("p1", 5.0)
    with pytest.raises(BudgetError, match="hard cap"):
        log.check("p1", 15.0)


def test_publish_slot_rules():
    from core import publish_slot as P
    s = {"timezone": "Asia/Kolkata", "long_time": "19:00", "immediate_after": "19:00", "short_after_long_min": 60, "one_long_per_day": True}
    utc = dt.timezone.utc
    morning = dt.datetime(2026, 1, 5, 4, 0, tzinfo=utc)  # 09:30 local
    slot = P.plan_long(s, morning)
    assert slot.action == "schedule" and slot.local("Asia/Kolkata").startswith("2026-01-05 19:00")
    assert P.plan_short(s, slot).at - slot.at == dt.timedelta(minutes=60)
    evening = dt.datetime(2026, 1, 5, 14, 30, tzinfo=utc)  # 20:00 local
    assert P.plan_long(s, evening).action == "now"
    taken = {dt.date(2026, 1, 5)}
    nxt = P.plan_long(s, evening, taken)
    assert nxt.action == "schedule" and nxt.local("Asia/Kolkata").startswith("2026-01-06 19:00")
