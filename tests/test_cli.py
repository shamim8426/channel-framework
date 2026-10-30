import yaml

from core.cli import main
from core.config import load_channel


def test_new_channel_non_interactive_is_ready_for_script(ws, capsys):
    rc = main(["--root", str(ws.root), "new-channel", "my-chan", "--yes", "--name", "My Chan", "--language", "hi", "--niche", "demo stuff",
               "--pipeline", "character_story", "--voices", "a,b", "--visual-style", "painted scenes with warm light"])
    out = capsys.readouterr().out
    assert rc == 0 and "READY FOR SCRIPT" in out
    cfg = load_channel("my-chan", ws)
    assert cfg["language"] == "hi" and cfg["narrators"][0]["voice_id"] == "a" and cfg["credentials_ref"] == "my-chan"
    assert (ws.agents_out / "kalam-my-chan.md").exists() and (ws.channel_dir("my-chan") / "rules.md").exists()
    assert not any(ws.secrets.glob("*")) if ws.secrets.exists() else True  # wizard never creates secrets


def test_new_channel_rejects_bad_input_and_existing(ws, channel, capsys):
    assert main(["--root", str(ws.root), "new-channel", "bad slug", "--yes"]) == 1
    assert main(["--root", str(ws.root), "new-channel", channel, "--yes"]) == 1  # exists, nothing changed
    assert main(["--root", str(ws.root), "new-channel", "x-chan", "--yes", "--pipeline", "nonexistent"]) == 1
    assert not (ws.channels / "x-chan").exists()  # nothing half-created


def test_surah_pipeline_demands_real_sourced(ws):
    from tests.conftest import make_channel
    make_channel(ws, "s-chan", pipeline="surah_explainer")
    f = ws.channel_dir("s-chan") / "channel.yaml"
    d = yaml.safe_load(f.read_text())
    d["content_type"] = "fiction"
    f.write_text(yaml.safe_dump(d))
    assert main(["--root", str(ws.root), "validate", "--channel", "s-chan"]) == 1


def test_list_validate_doctor_reports(ws, channel, capsys):
    assert main(["--root", str(ws.root), "list-channels"]) == 0
    assert channel in capsys.readouterr().out
    assert main(["--root", str(ws.root), "validate", "--channel", channel]) == 0
    main(["--root", str(ws.root), "doctor"])
    out = capsys.readouterr().out
    assert "config valid" in out and "secrets/" in out and "REPLACE_ME" in out
    assert main(["--root", str(ws.root), "reports", "--channel", channel]) == 0


def test_invalid_config_message_via_cli(ws, channel, capsys):
    f = ws.channel_dir(channel) / "channel.yaml"
    d = yaml.safe_load(f.read_text())
    d["content_type"] = "wrong"
    f.write_text(yaml.safe_dump(d))
    assert main(["--root", str(ws.root), "validate", "--channel", channel]) == 1
    assert "content_type" in capsys.readouterr().err
