"""'READY FOR SCRIPT' check: everything a user must have BEFORE the script stage, from the framework's point of view."""
from .agents import ROLES
from .config import ChannelConfig, find_config_file
from .paths import Workspace
from .pipelines import load_pipeline


def readiness(cfg: ChannelConfig, ws: Workspace) -> list:
    d = ws.channel_dir(cfg.slug)
    out = [(True, "channel config valid")]
    try:
        problems = load_pipeline(cfg["pipeline"]).validate_config(cfg)
        out.append((not problems, "pipeline plugin ok" if not problems else "; ".join(problems)))
    except Exception as e:  # unknown pipeline etc.
        out.append((False, f"pipeline: {e}"))
    out.append(((d / "rules.md").exists(), "channels/<slug>/rules.md present"))
    out.append(((d / "STYLE_LEARNINGS.md").exists(), "STYLE_LEARNINGS.md present"))
    out.append((all(n.get("voice_id") for n in cfg["narrators"]), "every narrator has a voice_id"))
    out.append((len(cfg["visual_style"]["prompt"]) >= 10, "visual style prompt set"))
    missing = [r for r in ROLES if not (ws.agents_out / f"{r}-{cfg.slug}.md").exists()]
    out.append((not missing, "agents rendered into .claude/agents" if not missing else f"agents not rendered ({', '.join(missing)}): " + ws.cmd(f"render-agents --channel {cfg.slug}")))
    return out


def is_ready(items) -> bool:
    return all(ok for ok, _ in items)
