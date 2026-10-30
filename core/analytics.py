"""Analytics hooks. Pipelines call `on_upload(...)` after every upload; hooks are plain functions registered here.

Default hook writes channels/<slug>/analytics/uploads.jsonl (video id, kind, time) - the data an analyst agent (Nigraan) needs
to schedule 48 h / 7 d post-mortems (`due_reports`). Real metrics come from a provider: `mock` (zeros) or `youtube`
(YouTube Analytics API, read-only token secrets/<ref>/analytics_token.json - live only, not exercised by tests)."""
import datetime as dt
import json
from pathlib import Path

from .config import ChannelConfig
from .paths import Workspace
from .secrets import SecretStore

HOOKS = []


def register_hook(fn):
    HOOKS.append(fn)
    return fn


@register_hook
def record_upload(ws: Workspace, cfg: ChannelConfig, result: dict, project: str):
    f = ws.channel_dir(cfg.slug) / "analytics" / "uploads.jsonl"
    f.parent.mkdir(parents=True, exist_ok=True)
    with f.open("a", encoding="utf-8") as fh:
        fh.write(json.dumps({**result, "project": project}, ensure_ascii=False) + "\n")


def on_upload(ws, cfg, result, project):
    for h in list(HOOKS):
        h(ws, cfg, result, project)


def due_reports(ws: Workspace, cfg: ChannelConfig, now: dt.datetime | None = None) -> list:
    """[(video_id, '48h'|'7d', due_at)] already due and not yet marked done (analytics/done.jsonl)."""
    now = now or dt.datetime.now(dt.timezone.utc)
    base = ws.channel_dir(cfg.slug) / "analytics"
    f = base / "uploads.jsonl"
    if not f.exists():
        return []
    done = set()
    if (base / "done.jsonl").exists():
        done = {(r["video_id"], r["report"]) for r in map(json.loads, (base / "done.jsonl").read_text().splitlines())}
    out = []
    for r in map(json.loads, f.read_text().splitlines()):
        t0 = dt.datetime.fromisoformat(r["uploaded_at"])
        for rep, delta in (("48h", dt.timedelta(hours=48)), ("7d", dt.timedelta(days=7))):
            if rep in cfg["analytics"]["reports"] and (r["video_id"], rep) not in done and t0 + delta <= now:
                out.append((r["video_id"], rep, (t0 + delta).isoformat()))
    return out


def mark_done(ws, cfg, video_id, report):
    f = ws.channel_dir(cfg.slug) / "analytics" / "done.jsonl"
    f.parent.mkdir(parents=True, exist_ok=True)
    with f.open("a", encoding="utf-8") as fh:
        fh.write(json.dumps({"video_id": video_id, "report": report}) + "\n")


class MockAnalytics:
    def fetch(self, video_id):
        return {"video_id": video_id, "views": 0, "impressions": 0, "ctr": 0.0, "avg_view_pct": 0.0, "note": "mock"}


class YouTubeAnalytics:  # pragma: no cover - live only
    def __init__(self, ws, cfg):
        self.token = SecretStore(ws, cfg["credentials_ref"]).require("analytics_token")

    def fetch(self, video_id):
        raise NotImplementedError("wire the YouTube Analytics API here (read-only token); see docs/MIGRATING_EXISTING_CHANNEL.md")


def get_analytics(ws, cfg, live=False):
    return YouTubeAnalytics(ws, cfg) if live and cfg["analytics"]["provider"] == "youtube" else MockAnalytics()
