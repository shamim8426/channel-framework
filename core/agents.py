"""Agent templates -> per-channel Claude Code agent files (.claude/agents/<role>-<slug>.md).

Templates (agents/*.md.tmpl) contain NO channel names: they use {{ channel.name }}, {{ rules.channel }}, ... and
{{#if channel.content_type == real_sourced}} ... {{/if}} blocks. Unknown variables are errors (never silently blank)."""
import re
from pathlib import Path

from .config import ChannelConfig
from .errors import FrameworkError
from .paths import Workspace

VAR = re.compile(r"\{\{\s*([a-z_][a-z0-9_.]*)\s*\}\}")
IF = re.compile(r"\{\{#if\s+([a-z_][a-z0-9_.]*)\s*(==|!=)\s*([A-Za-z0-9_-]+)\s*\}\}(.*?)\{\{/if\}\}", re.S)
ROLES = ("khoji", "kalam", "munshi", "sampadak", "nigraan", "kaarigar")


def context_for(cfg: ChannelConfig, ws: Workspace | None = None) -> dict:
    ws = ws or Workspace()
    s = cfg.slug
    return {
        "channel": {"name": cfg.name, "slug": s, "language": cfg["language"], "niche": cfg["niche"], "content_type": cfg["content_type"],
                    "pipeline": cfg["pipeline"], "handle": cfg.get("handle", "")},
        "rules": {"global": ws.global_rules_ref, "channel": f"channels/{s}/rules.md", "style": f"channels/{s}/STYLE_LEARNINGS.md",
                  "dir": f"channels/{s}"},
        "narrators": {"list": ", ".join(f"{n['id']} ({n['role']})" for n in cfg["narrators"])},
        "safety": {"depictions": "; ".join(cfg["safety"]["forbidden_depictions"]) or "(none configured)",
                   "terms": ", ".join(cfg["safety"]["forbidden_terms"]) or "(none configured)"},
        "research": {"min_sources": str(cfg["research"]["min_sources_per_fact"])},
    }


def _lookup(ctx: dict, path: str):
    cur = ctx
    for p in path.split("."):
        if not isinstance(cur, dict) or p not in cur:
            raise FrameworkError(f"agent template uses unknown variable '{path}'")
        cur = cur[p]
    return cur


def render_template(text: str, ctx: dict) -> str:
    text = IF.sub(lambda m: m.group(4) if (str(_lookup(ctx, m.group(1))) == m.group(3)) == (m.group(2) == "==") else "", text)
    return VAR.sub(lambda m: str(_lookup(ctx, m.group(1))), text)


def render_agents(cfg: ChannelConfig, ws: Workspace | None = None, out_dir: Path | None = None) -> list:
    ws = ws or Workspace()
    out_dir = out_dir or ws.agents_out
    out_dir.mkdir(parents=True, exist_ok=True)
    ctx, written = context_for(cfg, ws), []
    for role in ROLES:
        tmpl = ws.agent_templates / f"{role}.md.tmpl"
        f = out_dir / f"{role}-{cfg.slug}.md"
        f.write_text(render_template(tmpl.read_text(encoding="utf-8"), ctx), encoding="utf-8")
        written.append(f)
    return written
