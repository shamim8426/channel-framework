"""Secrets handling. Rules: secrets live ONLY in secrets/<credentials_ref>/ (gitignored) or in environment variables whose
NAMES are written in the config. Config files hold references, never values."""
import os
import subprocess
from pathlib import Path

from .errors import SecretsError
from .paths import Workspace

FILES = {"client_secret": "client_secret.json", "token": "token.json", "analytics_token": "analytics_token.json"}


class SecretStore:
    def __init__(self, ws: Workspace, credentials_ref: str):
        self.ws = ws
        self.ref = credentials_ref

    @property
    def dir(self) -> Path:
        return self.ws.secrets_dir(self.ref)

    def path(self, kind: str) -> Path:
        if kind not in FILES:
            raise SecretsError(f"unknown secret kind '{kind}' (use one of {sorted(FILES)})")
        return self.dir / FILES[kind]

    def has(self, kind: str) -> bool:
        return self.path(kind).exists()

    def require(self, kind: str) -> Path:
        p = self.path(kind)
        if not p.exists():
            raise SecretsError(
                f"missing {FILES[kind]} for credentials_ref '{self.ref}'. Put it at {p} "
                f"(this folder is gitignored; see docs/ADD_A_CHANNEL.md, step 'YouTube credentials').")
        return p

    def ensure_dir(self) -> Path:
        self.dir.mkdir(parents=True, exist_ok=True)
        try:
            os.chmod(self.dir, 0o700)
        except OSError:
            pass
        return self.dir

    def status(self) -> dict:
        return {k: self.has(k) for k in FILES}


def api_key(env_name: str | None) -> str:
    if not env_name:
        raise SecretsError("this provider needs 'api_key_env' (the NAME of an environment variable) in channel config")
    v = os.environ.get(env_name, "").strip()
    if not v:
        raise SecretsError(f"environment variable {env_name} is empty or not set (live provider needs it)")
    return v


def gitignore_protects_secrets(root: Path) -> bool:
    gi = root / ".gitignore"
    return gi.exists() and any(line.strip().rstrip("/") in ("secrets", "/secrets") for line in gi.read_text().splitlines())


def tracked_secret_files(root: Path) -> list:
    """Secret-looking files that git tracks (should always be empty). Best effort, needs git."""
    try:
        out = subprocess.run(["git", "-C", str(root), "ls-files"], capture_output=True, text=True, timeout=20).stdout
    except (OSError, subprocess.SubprocessError):
        return []
    bad = ("client_secret", "token.json", "analytics_token", ".env")
    return [f for f in out.splitlines() if f.startswith("secrets/") or any(b in Path(f).name for b in bad)]
