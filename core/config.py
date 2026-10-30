"""Channel config loader + validator. Accepts channels/<slug>/channel.yaml or channel.json (yaml wins if both exist).

Validation = JSON Schema (core/schema/channel.schema.json) + semantic checks. Every problem is collected and reported at
once as a ConfigError with a path ("youtube.privacy: 'secret' is not one of ...") so a new user can fix a file in one go."""
import copy
import json
import re
from pathlib import Path

import yaml
from jsonschema import Draft7Validator

from .errors import ConfigError
from .paths import Workspace, check_slug

SCHEMA = json.loads((Path(__file__).parent / "schema" / "channel.schema.json").read_text(encoding="utf-8"))

DEFAULTS = {
    "formats": {
        "long": {"enabled": True, "min_seconds": 120, "max_seconds": 600, "script_words": [250, 900], "max_images": 12},
        "shorts": {"enabled": False, "min_seconds": 10, "max_seconds": 40, "count": 1},
    },
    "providers": {k: {"name": "mock"} for k in ("llm", "image", "tts", "music")},
    "audio": {"target_lufs": -14.0, "true_peak": -1.5, "tempo": 1.0, "music_below_voice_db": 19.0},
    "research": {"min_sources_per_fact": 2},
    "safety": {"forbidden_depictions": [], "forbidden_terms": []},
    "budget": {"currency": "INR", "target_per_project": 100, "hard_cap_per_project": 120},
    "characters": [],
    "music": {"library_dir": "music", "tracks": []},
    "strings": {},
    "options": {},
    "analytics": {"provider": "mock", "reports": ["48h", "7d"]},
    "youtube_channel_id": "REPLACE_ME",
    "youtube": {
        "privacy": "private", "auto_publish": False, "contains_synthetic_media": True, "playlists": {}, "title_suffix": "", "default_tags": [],
        "schedule": {"timezone": "UTC", "long_time": "19:00", "immediate_after": "19:00", "short_after_long_min": 60,
                     "one_long_per_day": True},
    },
}
SECRET_LIKE = re.compile(r"(AIza[0-9A-Za-z_-]{10,}|ya29\.|GOCSPX-|sk-[A-Za-z0-9]{10,}|^[A-Za-z0-9_-]{40,}$)")


def deep_merge(base, over):
    out = copy.deepcopy(base)
    for k, v in (over or {}).items():
        out[k] = deep_merge(out[k], v) if isinstance(v, dict) and isinstance(out.get(k), dict) else copy.deepcopy(v)
    return out


class ChannelConfig:
    """Validated config. cfg["youtube"]["privacy"] or cfg.get("youtube.privacy")."""

    def __init__(self, data: dict, source: Path | None = None):
        self.data = data
        self.source = source

    @property
    def slug(self) -> str:
        return self.data["slug"]

    @property
    def name(self) -> str:
        return self.data["name"]

    def __getitem__(self, key):
        return self.data[key]

    def get(self, path: str, default=None):
        cur = self.data
        for part in path.split("."):
            if not isinstance(cur, dict) or part not in cur:
                return default
            cur = cur[part]
        return cur

    @property
    def real_sourced(self) -> bool:
        return self.data["content_type"] == "real_sourced"

    def narrator(self, nid: str) -> dict:
        for n in self.data["narrators"]:
            if n["id"] == nid:
                return n
        raise KeyError(nid)

    @property
    def is_placeholder_channel_id(self) -> bool:
        return self.data["youtube_channel_id"] == "REPLACE_ME"


def find_config_file(channel_dir: Path) -> Path:
    for name in ("channel.yaml", "channel.yml", "channel.json"):
        if (channel_dir / name).exists():
            return channel_dir / name
    raise ConfigError(f"no channel.yaml or channel.json in {channel_dir}", channel_dir)


def read_raw(path: Path) -> dict:
    try:
        text = path.read_text(encoding="utf-8")
        data = json.loads(text) if path.suffix == ".json" else yaml.safe_load(text)
    except (yaml.YAMLError, json.JSONDecodeError) as e:
        raise ConfigError(f"cannot parse file: {e}", path) from e
    if not isinstance(data, dict):
        raise ConfigError("top level must be a mapping/object", path)
    return data


def schema_problems(data: dict) -> list:
    out = []
    for e in sorted(Draft7Validator(SCHEMA).iter_errors(data), key=lambda e: list(e.absolute_path)):
        where = ".".join(str(p) for p in e.absolute_path) or "(top level)"
        msg = e.message
        m = re.match(r"'([^']+)' does not match any of the regexes", msg)
        if m:
            msg = f"unknown key '{m.group(1)}' (typo? custom keys must start with 'x_')"
        elif msg.startswith("Additional properties are not allowed"):
            msg = "unknown key(s): " + msg.split("(", 1)[1].rstrip(")").replace(" was unexpected", "").replace(" were unexpected", "")
        out.append(f"{where}: {msg}")
    return out


def semantic_problems(data: dict, dir_slug: str | None) -> list:
    out = []
    if dir_slug and data.get("slug") != dir_slug:
        out.append(f"slug: '{data.get('slug')}' does not match its folder name '{dir_slug}'")
    ids = [n.get("id") for n in data.get("narrators", []) if isinstance(n, dict)]
    if len(ids) != len(set(ids)):
        out.append("narrators: ids must be unique")
    cids = [c.get("id") for c in data.get("characters", []) if isinstance(c, dict)]
    if set(cids) & set(ids):
        out.append("characters: an id is used both as character and narrator")
    ref = data.get("credentials_ref", "")
    if isinstance(ref, str) and SECRET_LIKE.search(ref):
        out.append("credentials_ref: looks like a secret value. Put only the NAME of the secrets folder here "
                   "(secrets/<name>/); the secret itself never goes into config or git")
    f = data.get("formats", {})
    for k, v in f.items():
        if isinstance(v, dict) and v.get("min_seconds") and v.get("max_seconds") and v["min_seconds"] > v["max_seconds"]:
            out.append(f"formats.{k}: min_seconds is larger than max_seconds")
    b = data.get("budget", {})
    if b.get("target_per_project", 0) > b.get("hard_cap_per_project", 1e9):
        out.append("budget: target_per_project is above hard_cap_per_project")
    return out


def validate_data(data: dict, dir_slug: str | None = None, source="") -> ChannelConfig:
    merged = deep_merge(DEFAULTS, data)
    problems = schema_problems(merged) + semantic_problems(merged, dir_slug)
    if problems:
        raise ConfigError(problems, source)
    return ChannelConfig(merged, Path(source) if source else None)


def load_channel(slug: str, ws: Workspace | None = None) -> ChannelConfig:
    ws = ws or Workspace()
    check_slug(slug)
    d = ws.channel_dir(slug)
    if not d.is_dir():
        raise ConfigError(f"channel '{slug}' does not exist ({d}). Create it: " + ws.cmd(f"new-channel {slug}"))
    path = find_config_file(d)
    return validate_data(read_raw(path), slug, path)


def load_rules(cfg: ChannelConfig, ws: Workspace | None = None) -> str:
    """Global RULES.md followed by the channel's rules.md (channel rules may be stricter, never looser) and STYLE_LEARNINGS.md."""
    ws = ws or Workspace()
    parts = [ws.global_rules.read_text(encoding="utf-8")]
    d = ws.channel_dir(cfg.slug)
    for fname, title in (("rules.md", "CHANNEL RULES (override/extend the global rules)"),
                         ("STYLE_LEARNINGS.md", "STYLE LEARNINGS (apply when writing and editing)")):
        f = d / fname
        if f.exists():
            parts.append(f"\n\n# {title}\n\n" + f.read_text(encoding="utf-8"))
    return "".join(parts)


def list_channels(ws: Workspace | None = None) -> list:
    ws = ws or Workspace()
    if not ws.channels.is_dir():
        return []
    return sorted(p.name for p in ws.channels.iterdir()
                  if p.is_dir() and not p.name.startswith("_") and any((p / n).exists() for n in
                                                                         ("channel.yaml", "channel.yml", "channel.json")))
