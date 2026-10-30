"""surah_explainer: sourced scripture explainer (ported/generalized from a scripture-meaning channel flow).

Always content_type=real_sourced (research + source check are mandatory). Dialogue between a teacher and a questioner; each
passage's ORIGINAL text is inserted by code from research/source_text.json - never produced by the LLM - and verified
byte-for-byte (sha256 recorded in research/source_check.json). Options (channel.yaml `options:`):
    ucharan: true            add a spoken line with the original words in the channel's own script (needs research/ucharan.json)
    arabic_font: <path>      font for on-screen original text (informational here; rendering uses core.media.text_pil)
Inputs the user/agent provides per project (research/): source_text.json {"title_orig": str, "passages": {"1": "text", ...}},
optional ucharan.json {"1": "reading", ...}, optional dossier.json (else drafted by the LLM, then gated)."""
from ..errors import GateError
from ..gates import research_stage, sha256, source_check_stage
from . import common as C
from .base import Pipeline, Stage, register


@register
class SurahExplainer(Pipeline):
    name = "surah_explainer"
    requires_content_type = "real_sourced"

    def validate_config(self, cfg):
        out = super().validate_config(cfg)
        roles = {n["role"] for n in cfg["narrators"]}
        if not {"teacher", "questioner"} & roles:
            out.append("narrators: surah_explainer expects roles 'teacher' (and optionally 'questioner')")
        return out

    def stages(self, ctx):
        def script(c):
            src = c.project.read_json("research", "source_text.json")
            if not src or not src.get("passages"):
                raise GateError("surah_explainer needs research/source_text.json {'passages': {'1': '<verbatim original text>', ...}}")
            d = c.project.read_json("research", "dossier.json")
            data = C.ask_script(c, "script_surah", header_extra="FACTS: " + ",".join(f["id"] for f in d["facts"]) + "\n"
                                                                  f"AYAT: {','.join(sorted(src['passages']))}\n", dossier=d)
            teacher = next((n["id"] for n in c.cfg["narrators"] if n["role"] in ("teacher", "narrator")), c.cfg["narrators"][0]["id"])
            ucharan = c.project.read_json("research", "ucharan.json", default={}) if c.cfg["options"].get("ucharan") else {}
            if c.cfg["options"].get("ucharan") and set(ucharan) != set(src["passages"]):
                raise GateError("options.ucharan is on but research/ucharan.json does not cover every passage")
            body = [l for l in data["lines"]]
            out, n = [], 0
            for l in body[:1]:
                n += 1
                out.append({**l, "n": n})
            scene = body[0]["scene"]
            for key in sorted(src["passages"], key=lambda k: int(k) if k.isdigit() else k):
                n += 1
                out.append({"n": n, "speaker": teacher, "text": src["passages"][key], "scene": scene, "kind": "arabic", "tags": []})
                if key in ucharan:
                    n += 1
                    out.append({"n": n, "speaker": teacher, "text": ucharan[key], "scene": scene, "kind": "ucharan", "tags": []})
            for l in body[1:]:
                n += 1
                out.append({**l, "n": n})
            data["lines"] = out
            C.write_script(c, data)
            return {"note": f"{len(out)} lines, {len(src['passages'])} verbatim passages"}

        def verbatim(c):
            src, s = c.project.read_json("research", "source_text.json"), c.project.read_json("script", "script.json")
            got = [l["text"] for l in s["lines"] if l["kind"] == "arabic"]
            want = [src["passages"][k] for k in sorted(src["passages"], key=lambda k: int(k) if k.isdigit() else k)]
            if got != want:
                raise GateError("verbatim check FAILED: on-screen original text differs from research/source_text.json")
            c.project.write_json("research", "source_check.json", data={"sha256": [sha256(t) for t in got]})
            return {"note": "original text identical to source (sha256 recorded)"}

        return [
            Stage("research", research_stage, role="research", gate=True),
            Stage("script", script),
            Stage("verbatim_check", verbatim, role="source_check", gate=True),
            Stage("script_review", C.stage_review_script, role="review"),
            Stage("source_check", source_check_stage, role="source_check", gate=True),
            Stage("images", C.stage_images),
            Stage("tts", C.stage_tts),
            Stage("build", C.stage_build),
            Stage("build_review", C.stage_review_build, role="review"),
            Stage("preview", C.stage_preview),
            Stage("approval", None, needs_approval=True),
            Stage("upload", C.stage_upload),
        ]
