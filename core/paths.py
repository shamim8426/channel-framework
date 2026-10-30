"""Workspace paths. The *framework* (this repo: core/, agents/, channels/_template, RULES.md) and the *workspace*
(channels/, secrets/, .claude/agents) are usually the same directory, but tests and users may point CF_ROOT elsewhere."""
import os
import re
from pathlib import Path

from .errors import FrameworkError

FRAMEWORK_ROOT = Path(__file__).resolve().parent.parent


class SlugError(FrameworkError, ValueError):
    pass


SLUG_RE = re.compile(r"^[a-z0-9][a-z0-9-]{1,40}$")


class Workspace:
    def __init__(self, root=None):
        self.root = Path(root or os.environ.get("CF_ROOT") or FRAMEWORK_ROOT).resolve()

    # framework resources (always shipped with the code)
    @property
    def global_rules(self) -> Path:
        return FRAMEWORK_ROOT / "RULES.md"

    @property
    def agent_templates(self) -> Path:
        return FRAMEWORK_ROOT / "agents"

    @property
    def channel_template(self) -> Path:
        return FRAMEWORK_ROOT / "channels" / "_template"

    @property
    def is_separate(self) -> bool:
        """True when channels live outside the framework checkout (--root / CF_ROOT)."""
        return self.root != FRAMEWORK_ROOT.resolve()

    def cmd(self, rest: str) -> str:
        """The command a user should type next; adds --root when the workspace is not the framework checkout."""
        return f"python -m core --root {self.root} {rest}" if self.is_separate else f"python -m core {rest}"

    @property
    def global_rules_ref(self) -> str:
        """How agents (working in the workspace root) find the global RULES.md: a path relative to the workspace."""
        if not self.is_separate:
            return "RULES.md"
        try:
            return Path(os.path.relpath(self.global_rules, self.root)).as_posix()
        except ValueError:  # different drive on Windows
            return self.global_rules.as_posix()

    # workspace data
    @property
    def channels(self) -> Path:
        return self.root / "channels"

    @property
    def secrets(self) -> Path:
        return self.root / "secrets"

    @property
    def agents_out(self) -> Path:
        return self.root / ".claude" / "agents"

    def channel_dir(self, slug: str) -> Path:
        check_slug(slug)
        return self.channels / slug

    def projects_dir(self, slug: str) -> Path:
        return self.channel_dir(slug) / "projects"

    def secrets_dir(self, slug: str) -> Path:
        check_slug(slug)
        return self.secrets / slug

    def next_project_dir(self, slug: str, idea: str) -> Path:
        base = self.projects_dir(slug)
        base.mkdir(parents=True, exist_ok=True)
        n = 1 + max([int(p.name[:3]) for p in base.iterdir() if p.is_dir() and p.name[:3].isdigit()] or [0])
        words = re.sub(r"[^a-z0-9]+", "-", idea.lower()).strip("-")[:40].strip("-") or "project"
        return base / f"{n:03d}_{words}"

    def find_project(self, slug: str, name: str) -> Path:
        base = self.projects_dir(slug)
        for p in sorted(base.iterdir()) if base.exists() else []:
            if p.is_dir() and (p.name == name or p.name.startswith(name)):
                return p
        raise FileNotFoundError(f"no project '{name}' in {base}")


def check_slug(slug: str) -> str:
    if not isinstance(slug, str) or not SLUG_RE.match(slug):
        raise SlugError(f"invalid channel slug {slug!r}: use 2-41 chars, lowercase letters, digits and '-'")
    return slug
