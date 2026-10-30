"""python -m core <command> --channel <slug> ...

new-channel [slug]        wizard (essentials only) -> channel READY FOR SCRIPT
start-script "<idea>"     everything from research/script to a PREVIEW for approval (mock providers unless --live)
approve                   continue after your approval: upload (+ Shorts) with the channel-ID guard
validate                  config + readiness check for one channel
list-channels             all channels with status
doctor                    tools, dependencies, secrets, keys (per channel)
render-agents             write .claude/agents/<role>-<slug>.md from agents/*.tmpl + channel config
reports                   which 48h / 7d analytics post-mortems are due
auth                      one-time YouTube OAuth login (live)"""
import argparse
import sys

from . import analytics, doctor as doctor_mod
from .agents import render_agents
from .config import list_channels, load_channel, load_rules
from .costlog import CostLog
from .errors import FrameworkError
from .paths import Workspace
from .pipelines import Context, Project, load_pipeline, run_pipeline
from .providers import all_providers
from .ready import is_ready, readiness
from .secrets import SecretStore
from .wizard import new_channel


def _ctx(ws, cfg, project, live, idea="") -> Context:
    return Context(ws=ws, cfg=cfg, project=project, providers=all_providers(cfg, live), costlog=CostLog(ws, cfg), live=live,
                   idea=idea, rules=load_rules(cfg, ws))


def _report(project: Project, ctx: Context):
    st = project.state
    for name, s in st["stages"].items():
        print(f"  {s['status']:18} {name}" + (f"  - {s['note']}" if s.get("note") else ""))
    spent = ctx.costlog.total(project.name)
    print(f"cost so far: {spent:.2f} {ctx.cfg['budget']['currency']} | mode: {'LIVE' if ctx.live else 'mock/dry-run (no paid calls, no real upload)'}")
    return st


def cmd_start_script(ws, a) -> int:
    cfg = load_channel(a.channel, ws)
    items = readiness(cfg, ws)
    if not is_ready(items):
        for ok, msg in items:
            print(f"  [{'x' if ok else ' '}] {msg}")
        raise FrameworkError("channel is not ready for script (see above)")
    if a.project:
        project = Project(ws.find_project(a.channel, a.project))
        idea = project.state.get("idea", a.idea or "")
    else:
        if not a.idea:
            raise FrameworkError('give a topic: python -m core start-script --channel <slug> "<topic or story idea>"')
        project, idea = Project(ws.next_project_dir(a.channel, a.idea)), a.idea
    ctx = _ctx(ws, cfg, project, a.live, idea)
    print(f"{cfg.name}: {project.name} (pipeline {cfg['pipeline']})")
    try:
        st = run_pipeline(ctx, load_pipeline(cfg["pipeline"]))
    finally:
        _report(project, ctx)
    if st["status"] == "awaiting_approval":
        print(f"\nAWAITING YOUR APPROVAL. Review {project.dir}/PREVIEW.md, then:\n"
              f"    " + ws.cmd(f"approve --channel {cfg.slug} --project {project.name}" + (" --live" if a.live else "")))
    return 0


def cmd_approve(ws, a) -> int:
    cfg = load_channel(a.channel, ws)
    project = Project(ws.find_project(a.channel, a.project))
    st = project.state
    if st.get("status") != "awaiting_approval":
        raise FrameworkError(f"project is '{st.get('status')}', not awaiting approval")
    st["approved"] = True
    project.save_state(st)
    ctx = _ctx(ws, cfg, project, a.live, st.get("idea", ""))
    try:
        run_pipeline(ctx, load_pipeline(cfg["pipeline"]))
    finally:
        _report(project, ctx)
    return 0


def cmd_validate(ws, a) -> int:
    cfg = load_channel(a.channel, ws)
    items = readiness(cfg, ws)
    for ok, msg in items:
        print(f"  [{'x' if ok else ' '}] {msg}")
    print("READY FOR SCRIPT" if is_ready(items) else "NOT READY")
    return 0 if is_ready(items) else 1


def cmd_list(ws, a) -> int:
    chans = list_channels(ws)
    if not chans:
        print("no channels yet: python -m core new-channel")
    for slug in chans:
        try:
            cfg = load_channel(slug, ws)
            print(f"{slug:24} {cfg['pipeline']:16} {cfg['content_type']:13} {'ready' if is_ready(readiness(cfg, ws)) else 'NOT READY'}  {cfg.name}")
        except FrameworkError as e:
            print(f"{slug:24} INVALID: {str(e).splitlines()[1] if len(str(e).splitlines()) > 1 else e}")
    return 0


def cmd_render(ws, a) -> int:
    slugs = [a.channel] if a.channel else list_channels(ws)
    for s in slugs:
        for f in render_agents(load_channel(s, ws), ws):
            print("wrote", f.relative_to(ws.root))
    return 0


def cmd_reports(ws, a) -> int:
    cfg = load_channel(a.channel, ws)
    due = analytics.due_reports(ws, cfg)
    print("\n".join(f"{v}: {r} post-mortem due since {t}" for v, r, t in due) or "no reports due")
    return 0


def cmd_auth(ws, a) -> int:  # pragma: no cover - interactive
    from .youtube import authorize
    cfg = load_channel(a.channel, ws)
    print("token written:", authorize(cfg, SecretStore(ws, cfg["credentials_ref"])))
    return 0


def main(argv=None) -> int:
    p = argparse.ArgumentParser(prog="python -m core", description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    p.add_argument("--root", help="workspace root (default: CF_ROOT or this repo)")
    sub = p.add_subparsers(dest="cmd", required=True)

    def chan(sp, required=True):
        sp.add_argument("--channel", required=required, help="channel slug (folder name under channels/)")

    s = sub.add_parser("new-channel")
    s.add_argument("slug", nargs="?")
    s.add_argument("--yes", action="store_true", help="no questions: use flags and defaults")
    for k in ("name", "language", "niche", "pipeline", "voices", "visual_style", "youtube_channel_id", "handle", "content_type"):
        s.add_argument("--" + k.replace("_", "-"), dest=k)
    s.add_argument("--forbid-depiction", action="append", dest="forbidden_depictions")
    s.add_argument("--made-for-kids", action="store_true")
    s = sub.add_parser("start-script")
    chan(s)
    s.add_argument("idea", nargs="?")
    s.add_argument("--project", help="resume an existing project instead of starting a new one")
    s.add_argument("--live", action="store_true", help="use the real providers/YouTube (default: mock + dry run)")
    s = sub.add_parser("approve")
    chan(s)
    s.add_argument("--project", required=True)
    s.add_argument("--live", action="store_true")
    for name in ("validate", "reports", "auth"):
        chan(sub.add_parser(name))
    sub.add_parser("list-channels")
    chan(sub.add_parser("render-agents"), required=False)
    s = sub.add_parser("doctor")
    chan(s, required=False)

    a = p.parse_args(argv)
    ws = Workspace(a.root)
    try:
        if a.cmd == "new-channel":
            args = {k: v for k, v in vars(a).items() if v not in (None, False) and k not in ("cmd", "root", "yes")}
            return new_channel(ws, args, interactive=not a.yes and sys.stdin.isatty())
        return {"start-script": cmd_start_script, "approve": cmd_approve, "validate": cmd_validate, "list-channels": cmd_list,
                "render-agents": cmd_render, "reports": cmd_reports, "auth": cmd_auth,
                "doctor": lambda w, x: doctor_mod.run(w, x.channel)}[a.cmd](ws, a)
    except FrameworkError as e:
        print(f"ERROR: {e}", file=sys.stderr)
        return 1
