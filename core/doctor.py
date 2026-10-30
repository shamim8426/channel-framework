"""doctor: environment + per-channel health. Exit code 1 if any ERROR (warnings do not fail)."""
import importlib
import os
import sys

from .config import list_channels, load_channel
from .errors import FrameworkError
from .media import ffmpeg as FF
from .media.text_pil import raqm_available
from .paths import Workspace
from .providers import KINDS
from .secrets import SecretStore, gitignore_protects_secrets, tracked_secret_files


def run(ws: Workspace, only: str | None = None) -> int:
    errors = 0

    def line(level, msg):
        nonlocal errors
        errors += level == "ERROR"
        print(f"[{level:5}] {msg}")

    line("OK" if sys.version_info >= (3, 10) else "ERROR", f"python {sys.version.split()[0]} (need >= 3.10)")
    for mod, req in (("yaml", True), ("jsonschema", True), ("PIL", True), ("numpy", True), ("requests", True),
                     ("googleapiclient", False)):
        try:
            importlib.import_module(mod)
            line("OK", f"python module {mod}")
        except ImportError:
            line("ERROR" if req else "WARN", f"python module {mod} missing" + ("" if req else " (only needed for live YouTube: requirements-youtube.txt)"))
    line("OK" if FF.have_ffmpeg() else "WARN", "ffmpeg + ffprobe" if FF.have_ffmpeg() else "ffmpeg/ffprobe missing: builds write manifests only, no video")
    line("OK" if raqm_available() else "WARN", "Pillow RAQM (complex scripts)" if raqm_available() else "Pillow has no libraqm: Arabic/Devanagari text may be mis-shaped")
    line("OK" if gitignore_protects_secrets(ws.root) else "ERROR", ".gitignore protects secrets/")
    tracked = tracked_secret_files(ws.root)
    line("ERROR" if tracked else "OK", f"secret files tracked by git: {tracked}" if tracked else "no secret files tracked by git")
    slugs = [only] if only else list_channels(ws)
    if not slugs:
        line("WARN", "no channels yet: python -m core new-channel")
    for slug in slugs:
        try:
            cfg = load_channel(slug, ws)
        except FrameworkError as e:
            line("ERROR", f"{slug}: {e}")
            continue
        line("OK", f"{slug}: config valid (pipeline {cfg['pipeline']}, {cfg['content_type']})")
        st = SecretStore(ws, cfg["credentials_ref"]).status()
        for kind, have in st.items():
            line("OK" if have else "WARN", f"{slug}: secrets/{cfg['credentials_ref']}/{kind} {'present' if have else 'missing (needed for live upload/analytics only)'}")
        if cfg.is_placeholder_channel_id:
            line("WARN", f"{slug}: youtube_channel_id is REPLACE_ME (live uploads refuse it)")
        for kind in KINDS:
            p = cfg["providers"][kind]
            if p["name"] != "mock" and p.get("api_key_env") and not os.environ.get(p["api_key_env"]):
                line("WARN", f"{slug}: provider {kind} '{p['name']}' needs env var {p['api_key_env']} (set only for --live runs)")
    print(f"doctor: {'FAILED' if errors else 'ok'} ({errors} error(s))")
    return 1 if errors else 0
