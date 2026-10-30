import json

import pytest

from core import gates
from core.config import load_channel
from core.errors import GateError
from core.pipelines import Context, Pipeline, Project, Stage, register, run_pipeline
from core.pipelines.base import check_gates
from core.providers import all_providers, get_provider
from core.providers.base import ProviderUnavailable, Result
from core.providers import Chain
from core.costlog import CostLog
from tests.conftest import make_channel


def ctx_for(ws, slug, tmp_path):
    cfg = load_channel(slug, ws)
    return Context(ws=ws, cfg=cfg, project=Project(tmp_path / "p"), providers=all_providers(cfg), costlog=CostLog(ws, cfg), idea="x")


def test_real_sourced_pipeline_without_gates_is_refused(ws, tmp_path):
    make_channel(ws, "real-chan", pipeline="surah_explainer")
    c = ctx_for(ws, "real-chan", tmp_path)

    @register
    class NoGates(Pipeline):
        name = "no_gates_test"

        def stages(self, ctx):
            return [Stage("script", lambda c: None)]

    with pytest.raises(GateError, match="mandatory 'research'"):
        run_pipeline(c, NoGates())


def test_fiction_pipeline_without_gates_is_fine(ws, channel, tmp_path):
    c = ctx_for(ws, channel, tmp_path)
    from core.pipelines import PIPELINES
    check_gates(c.cfg, PIPELINES["no_gates_test"]().stages(c) if "no_gates_test" in PIPELINES else [])


def test_dossier_needs_enough_distinct_sources():
    ok = {"facts": [{"id": "F1", "claim": "c", "sources": [{"title": "A", "ref": "1"}, {"title": "B", "ref": "2"}]}]}
    gates.validate_dossier(ok, 2)
    one = {"facts": [{"id": "F1", "claim": "c", "sources": [{"title": "A", "ref": "1"}, {"title": "A", "ref": "1"}]}]}
    with pytest.raises(GateError, match="F1: 1 distinct"):
        gates.validate_dossier(one, 2)
    with pytest.raises(GateError, match="no facts"):
        gates.validate_dossier({"facts": []}, 2)


def test_source_check_blocks_untagged_and_unknown_tags(ws, tmp_path):
    make_channel(ws, "real-chan", pipeline="surah_explainer")
    c = ctx_for(ws, "real-chan", tmp_path)
    c.project.write_json("research", "dossier.json", data={"facts": [{"id": "F1", "claim": "c", "sources": []}]})
    c.project.write_json("script", "script.json", data={"lines": [
        {"n": 1, "kind": "claim", "tags": []}, {"n": 2, "kind": "claim", "tags": ["F9"]}, {"n": 3, "kind": "claim", "tags": ["F1"]}]})
    with pytest.raises(GateError) as e:
        gates.source_check_stage(c)
    assert "line 1" in str(e.value) and "F9" in str(e.value) and "line 3" not in str(e.value)


def test_research_gate_uses_existing_dossier_and_fails_on_thin_one(ws, tmp_path):
    make_channel(ws, "real-chan", pipeline="surah_explainer")
    c = ctx_for(ws, "real-chan", tmp_path)
    c.project.write_json("research", "dossier.json", data={"facts": [{"id": "F1", "claim": "c", "sources": [{"title": "A", "ref": "1"}]}]})
    with pytest.raises(GateError):
        gates.research_stage(c)


def test_mock_providers_write_valid_files(tmp_path, ws, channel):
    cfg = load_channel(channel, ws)
    p = all_providers(cfg)
    img = p["image"].generate("a prompt", tmp_path / "a.png")
    assert img.path.read_bytes()[:8] == b"\x89PNG\r\n\x1a\n" and img.cost == 0
    tts = p["tts"].synthesize("hello there friend", "v", tmp_path / "a.wav")
    import wave
    assert wave.open(str(tmp_path / "a.wav")).getnframes() > 1000 and tts.cost == 0
    m = p["music"].fetch("calm", tmp_path / "m.wav", 5)
    assert m.path.exists()
    r = p["llm"].complete("TASK: research\nIDEA: tea\n")
    assert json.loads(r.meta["text"])["facts"]


def test_live_flag_required_for_real_providers(ws, channel):
    import yaml
    f = ws.channel_dir(channel) / "channel.yaml"
    d = yaml.safe_load(f.read_text())
    d["providers"] = {"image": {"name": "cloudflare,gemini", "api_key_env": "X_KEY"}}
    f.write_text(yaml.safe_dump(d))
    cfg = load_channel(channel, ws)
    assert get_provider("image", cfg, live=False).name == "mock"
    chain = get_provider("image", cfg, live=True)
    assert chain.name == "cloudflare,gemini"


def test_free_first_chain_falls_through():
    class A:
        name = "a"
        def generate(self, *a, **k): raise ProviderUnavailable("quota")
    class B:
        name = "b"
        def generate(self, *a, **k): return Result(provider="b")
    assert Chain("image", [A(), B()]).generate("p", "o").provider == "b"
    with pytest.raises(ProviderUnavailable):
        Chain("image", [A()]).generate("p", "o")


def test_text_pil_wraps_balanced_and_shapes():
    from core.media import text_pil
    img = text_pil.render("one two three four five six seven eight", None, 40, maxw=260, max_lines=2, box=(0, 0, 0, 0.5), radius=8)
    assert img.mode == "RGBA" and img.height < 40 * 1.3 * 3
    f = text_pil.load_font(None, 30)
    lines = text_pil.wrap_balanced("aaa bbb ccc ddd eee fff", f, 200)
    assert len(lines) <= 3 and all(lines)


def test_chain_gives_each_provider_its_own_model_and_key(ws, channel):
    import yaml
    from core.config import load_channel
    from core.providers import get_provider
    f = ws.channel_dir(channel) / "channel.yaml"
    d = yaml.safe_load(f.read_text())
    d.setdefault("providers", {})["image"] = {"name": "cloudflare,gemini", "api_key_env": "GEMINI_API_KEY", "model": "img-model",
                               "per_provider": {"cloudflare": {"api_key_env": "CF_TOKEN", "model": "@cf/x"}}}
    f.write_text(yaml.safe_dump(d))
    chain = get_provider("image", load_channel(channel, ws), live=True)  # builds objects only, no network call
    cf, gm = chain.providers
    assert (cf.model, cf.env) == ("@cf/x", "CF_TOKEN") and (gm.model, gm.env) == ("img-model", "GEMINI_API_KEY")
