"""End-to-end dry runs with mock providers: no paid API calls, no real uploads, no network."""
import json
import shutil
from pathlib import Path

import pytest
import yaml

from core.cli import main
from core.config import load_channel
from core.errors import GateError
from core.media import ffmpeg as FF
from core.paths import FRAMEWORK_ROOT
from tests.conftest import make_channel


def project_dir(ws, slug):
    return next((ws.channels / slug / "projects").iterdir())


def test_example_story_end_to_end(tmp_path, capsys):
    root = tmp_path / "w"
    shutil.copytree(FRAMEWORK_ROOT / "channels" / "example-story", root / "channels" / "example-story")
    (root / ".gitignore").write_text("secrets/\n")
    assert main(["--root", str(root), "render-agents", "--channel", "example-story"]) == 0
    assert main(["--root", str(root), "validate", "--channel", "example-story"]) == 0
    assert main(["--root", str(root), "start-script", "--channel", "example-story", "Pip finds a lost star"]) == 0
    out = capsys.readouterr().out
    assert "AWAITING YOUR APPROVAL" in out and "mock/dry-run" in out
    p = project_dir(type("W", (), {"channels": root / "channels"})(), "example-story")
    st = json.loads((p / "state.json").read_text())
    assert st["status"] == "awaiting_approval"
    assert [k for k, v in st["stages"].items() if v["status"] == "skipped"] == ["research", "source_check"]  # fiction: gates skipped
    assert (p / "script" / "script.md").exists() and (p / "review" / "script_review.md").exists() and (p / "PREVIEW.md").exists()
    assert len(list((p / "images").glob("*.png"))) == 6 and (p / "audio" / "voice.wav").exists()
    assert not (p / "output").exists()  # nothing uploaded before approval
    if FF.have_ffmpeg():
        assert (p / "build" / "preview.mp4").exists()
    assert main(["--root", str(root), "approve", "--channel", "example-story", "--project", p.name]) == 0
    res = json.loads((p / "output" / "upload_result.json").read_text())
    assert res["dry_run"] and res["privacy"] == "private" and "STUDIO ACTION" in res["studio_action"]
    assert (p / "shorts" / "short_01_result.json").exists()
    up = (root / "channels" / "example-story" / "analytics" / "uploads.jsonl").read_text().splitlines()
    assert len(up) == 2  # long + short recorded by the analytics hook
    cost = (root / "channels" / "example-story" / "cost_log.csv").read_text()
    assert "mock" in cost


def test_resume_skips_finished_stages(ws, channel, capsys):
    assert main(["--root", str(ws.root), "start-script", "--channel", channel, "a tale"]) == 0
    p = project_dir(ws, channel)
    before = (p / "audio" / "lines").stat().st_mtime
    assert main(["--root", str(ws.root), "start-script", "--channel", channel, "--project", p.name]) == 0
    assert (p / "audio" / "lines").stat().st_mtime == before


def test_real_sourced_surah_pipeline_with_verbatim_text(ws, capsys):
    make_channel(ws, "scripture-demo", pipeline="surah_explainer", forbidden_depictions=["any prophet or companion as a person"])
    f = ws.channel_dir("scripture-demo") / "channel.yaml"
    d = yaml.safe_load(f.read_text())
    d["formats"]["long"].update(min_seconds=5, script_words=[10, 900])
    d["options"] = {"ucharan": True}
    f.write_text(yaml.safe_dump(d))
    # project inputs normally written by the research agent / the user
    proj = ws.projects_dir("scripture-demo") / "001_demo"
    (proj / "research").mkdir(parents=True)
    (proj / "research" / "source_text.json").write_text(json.dumps({"passages": {"1": "ORIGINAL TEXT ONE ✦", "2": "ORIGINAL TEXT TWO"}}))
    (proj / "research" / "ucharan.json").write_text(json.dumps({"1": "reading one", "2": "reading two"}))
    assert main(["--root", str(ws.root), "start-script", "--channel", "scripture-demo", "--project", "001_demo", "demo topic"]) == 0
    st = json.loads((proj / "state.json").read_text())
    assert st["status"] == "awaiting_approval"
    assert all(st["stages"][s]["status"] == "done" for s in ("research", "verbatim_check", "source_check"))  # gates ran
    script = json.loads((proj / "script" / "script.json").read_text())
    arabic = [l["text"] for l in script["lines"] if l["kind"] == "arabic"]
    assert arabic == ["ORIGINAL TEXT ONE ✦", "ORIGINAL TEXT TWO"]  # inserted verbatim by code
    assert len(json.loads((proj / "research" / "source_check.json").read_text())["sha256"]) == 2
    assert (proj / "review" / "source_check.md").read_text().count("PASS") == 1
    assert [l["text"] for l in script["lines"] if l["kind"] == "ucharan"] == ["reading one", "reading two"]
    voiced = {p.name.split("_")[0] for p in (proj / "audio" / "lines").glob("*.wav")}
    assert not voiced & {f"{l['n']:03d}" for l in script["lines"] if l["kind"] == "arabic"}  # original text is shown, never TTS'd


def test_missing_source_text_stops_surah_run(ws):
    make_channel(ws, "scripture-demo", pipeline="surah_explainer")
    assert main(["--root", str(ws.root), "start-script", "--channel", "scripture-demo", "topic"]) == 1  # GateError -> exit 1
    p = project_dir(ws, "scripture-demo")
    st = json.loads((p / "state.json").read_text())
    assert st["status"] == "failed" and st["stages"]["script"]["status"] == "failed"
    assert not (p / "output").exists()


def test_thin_dossier_stops_before_script(ws):
    make_channel(ws, "scripture-demo", pipeline="surah_explainer")
    proj = ws.projects_dir("scripture-demo") / "001_x"
    (proj / "research").mkdir(parents=True)
    (proj / "research" / "dossier.json").write_text(json.dumps({"facts": [{"id": "F1", "claim": "c", "sources": [{"title": "A", "ref": "1"}]}]}))
    assert main(["--root", str(ws.root), "start-script", "--channel", "scripture-demo", "--project", "001_x", "t"]) == 1
    st = json.loads((proj / "state.json").read_text())
    assert st["stages"]["research"]["status"] == "failed" and "script" not in st["stages"]


def test_forbidden_term_in_script_fails_review(ws):
    make_channel(ws, "strict-chan")
    f = ws.channel_dir("strict-chan") / "channel.yaml"
    d = yaml.safe_load(f.read_text())
    d["safety"] = {"forbidden_terms": ["lantern"]}  # the mock script uses this word
    f.write_text(yaml.safe_dump(d))
    assert main(["--root", str(ws.root), "start-script", "--channel", "strict-chan", "a tale"]) == 1
    st = json.loads((project_dir(ws, "strict-chan") / "state.json").read_text())
    assert st["stages"]["script_review"]["status"] == "failed"


def test_approve_requires_awaiting_state(ws, channel):
    main(["--root", str(ws.root), "start-script", "--channel", channel, "a tale"])
    p = project_dir(ws, channel)
    assert main(["--root", str(ws.root), "approve", "--channel", channel, "--project", p.name]) == 0
    assert main(["--root", str(ws.root), "approve", "--channel", channel, "--project", p.name]) == 1  # already done
