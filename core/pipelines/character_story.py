"""character_story: fiction (or sourced) stories told by a fixed cast. Ported/generalized from a kids' mystery channel flow:
research(gate) -> script -> script review -> source check(gate) -> images -> TTS -> build -> build review -> PREVIEW (approval)
-> upload -> Shorts. Channel specifics (characters, voices, style, lengths) are all in channel.yaml."""
from ..gates import research_stage, source_check_stage
from . import common as C
from .base import Pipeline, Stage, register


@register
class CharacterStory(Pipeline):
    name = "character_story"

    def stages(self, ctx):
        def script(c):
            d = c.project.read_json("research", "dossier.json")
            data = C.ask_script(c, "script_character", dossier=d)
            C.write_script(c, data)
            return {"note": f"{len(data['lines'])} lines"}

        return [
            Stage("research", research_stage, role="research", gate=True),
            Stage("script", script),
            Stage("script_review", C.stage_review_script, role="review"),
            Stage("source_check", source_check_stage, role="source_check", gate=True),
            Stage("images", C.stage_images),
            Stage("tts", C.stage_tts),
            Stage("build", C.stage_build),
            Stage("build_review", C.stage_review_build, role="review"),
            Stage("preview", C.stage_preview),
            Stage("approval", None, needs_approval=True),
            Stage("upload", C.stage_upload),
            Stage("shorts", C.stage_shorts, when=lambda c: c.cfg["formats"].get("shorts", {}).get("enabled", False)),
        ]
