"""Pipeline plugin interface.

A pipeline is a class with `name`, optional `requires_content_type`, and `stages(ctx) -> [Stage]`. The runner (run_pipeline)
executes stages in order, persists progress in projects/<NNN>_<slug>/state.json (re-running resumes, finished stages are
skipped), stops at the first stage with needs_approval until `approve`, and enforces the content_type gates:

    real_sourced  -> the pipeline MUST define a stage with role="research" and one with role="source_check", both gate=True;
                     they always run and a failure stops the run (GateError).
    fiction       -> gate=True stages are skipped.

To add a pipeline: subclass Pipeline, decorate with @register, set `pipeline: <name>` in channel.yaml (or use
"package.module:Class"). See docs/PIPELINES.md."""
import datetime as dt
import json
from dataclasses import dataclass, field
from pathlib import Path
from typing import Callable

from ..config import ChannelConfig
from ..costlog import CostLog
from ..errors import FrameworkError, GateError, PipelineError
from ..paths import Workspace

MANDATORY_ROLES = ("research", "source_check")


@dataclass
class Stage:
    name: str
    fn: Callable | None = None  # fn(ctx) -> dict | None
    role: str | None = None  # research | source_check | review | None
    gate: bool = False  # runs only for real_sourced (mandatory there)
    needs_approval: bool = False
    when: Callable | None = None  # extra condition; False -> skipped


class Project:
    def __init__(self, directory: Path):
        self.dir = Path(directory)
        self.dir.mkdir(parents=True, exist_ok=True)
        self.state_file = self.dir / "state.json"

    @property
    def name(self) -> str:
        return self.dir.name

    def path(self, *parts) -> Path:
        p = self.dir.joinpath(*parts)
        p.parent.mkdir(parents=True, exist_ok=True)
        return p

    def read_json(self, *parts, default=None):
        f = self.dir.joinpath(*parts)
        return json.loads(f.read_text(encoding="utf-8")) if f.exists() else default

    def write_json(self, *parts, data):
        self.path(*parts).write_text(json.dumps(data, indent=1, ensure_ascii=False), encoding="utf-8")

    @property
    def state(self) -> dict:
        return json.loads(self.state_file.read_text(encoding="utf-8")) if self.state_file.exists() else \
            {"status": "new", "approved": False, "stages": {}}

    def save_state(self, st: dict):
        self.state_file.write_text(json.dumps(st, indent=1, ensure_ascii=False), encoding="utf-8")


@dataclass
class Context:
    ws: Workspace
    cfg: ChannelConfig
    project: Project
    providers: dict
    costlog: CostLog
    live: bool = False
    idea: str = ""
    rules: str = ""
    now: dt.datetime = field(default_factory=lambda: dt.datetime.now(dt.timezone.utc))
    messages: list = field(default_factory=list)

    def log(self, msg: str):
        self.messages.append(msg)

    def charge(self, kind: str, result, detail: str = ""):
        self.costlog.append(self.project.name, result.provider or "?", kind, result.cost, detail)


class Pipeline:
    name = "base"
    requires_content_type: str | None = None

    def stages(self, ctx: Context) -> list:  # pragma: no cover - interface
        raise NotImplementedError

    def validate_config(self, cfg: ChannelConfig) -> list:
        """Plugin-specific config problems (strings). Called by `validate` and `new-channel`."""
        out = []
        if self.requires_content_type and cfg["content_type"] != self.requires_content_type:
            out.append(f"pipeline '{self.name}' requires content_type '{self.requires_content_type}'")
        return out


def check_gates(cfg: ChannelConfig, stages: list):
    if not cfg.real_sourced:
        return
    for role in MANDATORY_ROLES:
        if not any(s.role == role and s.gate for s in stages):
            raise GateError(f"content_type is real_sourced but this pipeline has no mandatory '{role}' gate stage "
                            f"(Stage(role='{role}', gate=True)). Refusing to run: unsourced content must not reach upload.")


def run_pipeline(ctx: Context, pipeline: Pipeline) -> dict:
    stages = pipeline.stages(ctx)
    check_gates(ctx.cfg, stages)
    st = ctx.project.state
    st.update(pipeline=pipeline.name, idea=ctx.idea, channel=ctx.cfg.slug)

    def mark(name, status, note=""):
        st["stages"][name] = {"status": status, "at": dt.datetime.now(dt.timezone.utc).isoformat(timespec="seconds"), "note": note}
        ctx.project.save_state(st)

    for s in stages:
        if st["stages"].get(s.name, {}).get("status") in ("done", "skipped"):
            continue
        if (s.gate and not ctx.cfg.real_sourced) or (s.when and not s.when(ctx)):
            mark(s.name, "skipped", "gate not required for fiction" if s.gate else "condition false")
            continue
        if s.needs_approval and not st.get("approved"):
            mark(s.name, "awaiting_approval")
            st["status"] = "awaiting_approval"
            ctx.project.save_state(st)
            return st
        try:
            note = (s.fn(ctx) or {}).get("note", "") if s.fn else ""
        except FrameworkError as e:
            mark(s.name, "failed", str(e))
            st["status"] = "failed"
            ctx.project.save_state(st)
            raise
        mark(s.name, "done", note)
    st["status"] = "done"
    ctx.project.save_state(st)
    return st


# registry ------------------------------------------------------------------------------------------------------
PIPELINES: dict = {}


def register(cls):
    PIPELINES[cls.name] = cls
    return cls


def load_pipeline(name: str) -> Pipeline:
    import importlib
    if ":" in name:
        mod, cls = name.split(":", 1)
        return getattr(importlib.import_module(mod), cls)()
    if name not in PIPELINES:
        raise PipelineError(f"unknown pipeline '{name}'. Available: {', '.join(sorted(PIPELINES))} "
                            f"(or 'package.module:Class' for your own)")
    return PIPELINES[name]()
