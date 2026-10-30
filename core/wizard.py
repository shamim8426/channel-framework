"""new-channel wizard: asks only the essentials (or takes flags), fills defaults, validates, renders agents and reports READY FOR SCRIPT."""
import shutil
import sys

import yaml

from .agents import render_agents
from .config import load_channel, validate_data
from .errors import FrameworkError
from .paths import Workspace, check_slug
from .pipelines import PIPELINES, load_pipeline
from .ready import is_ready, readiness

PRESETS = {
    "character_story": {
        "content_type": "fiction",
        "narrators": lambda v: [{"id": "narrator", "role": "narrator", "voice_id": v[0], "style": "clear, warm storyteller"}],
        "formats": {"long": {"min_seconds": 120, "max_seconds": 480, "script_words": [250, 900], "max_images": 12},
                    "shorts": {"enabled": True, "max_seconds": 40, "count": 1}},
    },
    "surah_explainer": {
        "content_type": "real_sourced",
        "narrators": lambda v: [{"id": "teacher", "role": "teacher", "voice_id": v[0], "style": "calm, respectful teacher"},
                                {"id": "questioner", "role": "questioner", "voice_id": v[1] if len(v) > 1 else v[0],
                                 "style": "curious student"}],
        "formats": {"long": {"min_seconds": 180, "max_seconds": 900, "script_words": [300, 1400], "max_images": 12}},
    },
}


def ask(prompt: str, default: str = "", interactive=True) -> str:
    if not interactive:
        return default
    v = input(f"{prompt}{' [' + default + ']' if default else ''}: ").strip()
    return v or default


def build_config(a: dict) -> dict:
    preset = PRESETS.get(a["pipeline"], PRESETS["character_story"])
    cfg = {
        "slug": a["slug"], "name": a["name"], "handle": a.get("handle") or "@your-handle",
        "youtube_channel_id": a.get("youtube_channel_id") or "REPLACE_ME",
        "language": a["language"], "niche": a["niche"],
        "content_type": a.get("content_type") or preset["content_type"], "pipeline": a["pipeline"],
        "formats": preset["formats"], "narrators": preset["narrators"](a["voices"]),
        "visual_style": {"prompt": a["visual_style"], "negative_prompt": "text, watermark, logo", "aspect": "16:9"},
        "youtube": {"category_id": a.get("category_id", "22"), "made_for_kids": a.get("made_for_kids", False),
                    "title_suffix": f"| {a['name']}"},
        "credentials_ref": a["slug"],
    }
    if a.get("forbidden_depictions"):
        cfg["safety"] = {"forbidden_depictions": a["forbidden_depictions"]}
    return cfg


def new_channel(ws: Workspace, args: dict, interactive: bool) -> int:
    slug = args.get("slug") or ask("Channel slug (lowercase, a-z 0-9 -)", "", interactive)
    check_slug(slug)
    d = ws.channel_dir(slug)
    if d.exists():
        raise FrameworkError(f"channels/{slug} already exists. Nothing changed.")
    a = {"slug": slug}
    a["name"] = args.get("name") or ask("Channel display name", slug.replace("-", " ").title(), interactive)
    a["language"] = args.get("language") or ask("Language code (en, hi, ...)", "en", interactive)
    a["niche"] = args.get("niche") or ask("Niche in a few words", "general stories", interactive)
    a["pipeline"] = args.get("pipeline") or ask(f"Pipeline ({', '.join(sorted(PIPELINES))})", "character_story", interactive)
    if a["pipeline"] not in PIPELINES:
        raise FrameworkError(f"unknown pipeline '{a['pipeline']}' (available: {', '.join(sorted(PIPELINES))})")
    v = args.get("voices") or ask("Voice id(s) of your TTS provider, comma separated", "voice-1", interactive)
    a["voices"] = [x.strip() for x in v.split(",") if x.strip()] if isinstance(v, str) else v
    a["visual_style"] = args.get("visual_style") or ask("Visual style prompt (one sentence)",
                                                         "soft hand-painted illustration, warm light, gentle colours", interactive)
    a["youtube_channel_id"] = args.get("youtube_channel_id") or ask("YouTube channel ID (UC..., Enter to fill in later)", "", interactive)
    a["handle"] = args.get("handle", "")
    a["content_type"] = args.get("content_type")
    a["forbidden_depictions"] = args.get("forbidden_depictions") or []
    a["made_for_kids"] = bool(args.get("made_for_kids"))
    data = build_config(a)
    validate_data(data, slug)  # fail BEFORE creating anything
    d.mkdir(parents=True)
    for sub in ("characters", "music", "branding", "projects", "research"):
        (d / sub).mkdir()
        (d / sub / ".gitkeep").write_text("")
    tpl = ws.channel_template
    for f in ("rules.md", "STYLE_LEARNINGS.md"):
        text = (tpl / f).read_text(encoding="utf-8").replace("{{channel_name}}", a["name"])
        if f == "rules.md" and a["forbidden_depictions"]:
            text += "\n## Depictions\n" + "\n".join(f"- Never depict: {x}" for x in a["forbidden_depictions"]) + "\n"
        (d / f).write_text(text, encoding="utf-8")
    (d / "channel.yaml").write_text("# channel config (validated by `python -m core validate`). Secrets never go here.\n" +
                                    yaml.safe_dump(data, sort_keys=False, allow_unicode=True), encoding="utf-8")
    cfg = load_channel(slug, ws)
    render_agents(cfg, ws)
    items = readiness(cfg, ws)
    print(f"created channels/{slug}/ (pipeline {cfg['pipeline']}, content_type {cfg['content_type']})")
    for ok, msg in items:
        print(f"  [{'x' if ok else ' '}] {msg}")
    if is_ready(items):
        print("READY FOR SCRIPT. Next: " + ws.cmd(f"start-script --channel {slug} \"<topic or idea>\""))
        if cfg.is_placeholder_channel_id:
            print("  note: youtube_channel_id is REPLACE_ME - fill it in before a live upload (dry runs work without it).")
        return 0
    print("NOT READY: fix the unchecked items above.")
    return 1
