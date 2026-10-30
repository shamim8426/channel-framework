import json

import pytest
import yaml

from core.config import load_channel, validate_data, list_channels, load_rules
from core.errors import ConfigError
from tests.conftest import make_channel

GOOD = {"slug": "abc", "name": "A", "language": "en", "niche": "some niche", "content_type": "fiction",
        "pipeline": "character_story", "formats": {"long": {}}, "narrators": [{"id": "n", "role": "narrator", "voice_id": "v"}],
        "visual_style": {"prompt": "a long enough style prompt"}, "youtube": {"category_id": "22", "made_for_kids": False},
        "credentials_ref": "abc"}


def test_valid_and_defaults_applied():
    cfg = validate_data(GOOD, "abc")
    assert cfg["youtube"]["privacy"] == "private" and cfg["providers"]["llm"]["name"] == "mock"
    assert cfg.get("youtube.schedule.timezone") == "UTC" and cfg.is_placeholder_channel_id


def test_errors_are_collected_and_readable():
    bad = dict(GOOD, content_type="nonsense", slug="Bad Slug", credentials_ref="AIzaSyD-this-looks-like-a-key-1234567890")
    bad["youtube"] = {"category_id": "x", "made_for_kids": "no"}
    with pytest.raises(ConfigError) as e:
        validate_data(bad, "abc")
    msg = str(e.value)
    assert "content_type" in msg and "slug" in msg and "youtube.category_id" in msg and "credentials_ref" in msg
    assert len(e.value.problems) >= 4


def test_unknown_key_is_caught_but_x_extensions_allowed():
    with pytest.raises(ConfigError, match="unknown key"):
        validate_data(dict(GOOD, colour="red"), "abc")
    validate_data(dict(GOOD, x_notes="free text"), "abc")


def test_slug_must_match_folder():
    with pytest.raises(ConfigError, match="does not match its folder"):
        validate_data(GOOD, "other")


def test_yaml_and_json_both_load(ws, channel):
    d = ws.channel_dir(channel)
    data = yaml.safe_load((d / "channel.yaml").read_text())
    (d / "channel.yaml").unlink()
    (d / "channel.json").write_text(json.dumps(data))
    assert load_channel(channel, ws).slug == channel


def test_missing_channel_and_bad_file(ws, channel):
    with pytest.raises(ConfigError, match="does not exist"):
        load_channel("nope-channel", ws)
    (ws.channel_dir(channel) / "channel.yaml").write_text("slug: [unclosed")
    with pytest.raises(ConfigError, match="cannot parse"):
        load_channel(channel, ws)


def test_rules_are_appended_after_global(ws, channel):
    text = load_rules(load_channel(channel, ws), ws)
    assert text.index("Global rules") < text.index("CHANNEL RULES") < text.index("STYLE LEARNINGS")


def test_list_channels_skips_template(ws, channel):
    assert list_channels(ws) == [channel]
