# Pipeline plugins

A channel selects its pipeline with `pipeline:` in `channel.yaml`. A pipeline is a class:

```python
from core.pipelines import Pipeline, Stage, register
from core.gates import research_stage, source_check_stage
from core.pipelines import common as C

@register
class MyPipeline(Pipeline):
    name = "my_pipeline"
    requires_content_type = None          # or "real_sourced"

    def validate_config(self, cfg):       # extra config checks -> list of problem strings
        return super().validate_config(cfg)

    def stages(self, ctx):                # ctx: Context(ws, cfg, project, providers, costlog, live, idea, rules)
        return [
            Stage("research", research_stage, role="research", gate=True),
            Stage("script", my_script_fn),
            Stage("source_check", source_check_stage, role="source_check", gate=True),
            Stage("images", C.stage_images), Stage("tts", C.stage_tts), Stage("build", C.stage_build),
            Stage("preview", C.stage_preview), Stage("approval", None, needs_approval=True),
            Stage("upload", C.stage_upload),
        ]
```

Use it by name after importing the module, or as `pipeline: "my_package.my_module:MyPipeline"` (no registration needed).

## Rules the runner enforces

- Stages run in order; progress is saved in `projects/<NNN>_<slug>/state.json`; finished stages are skipped on re-run.
- `needs_approval=True` stops the run (`awaiting_approval`) until `python -m core approve`.
- `gate=True` stages run only for `content_type: real_sourced` (mandatory there, a failure stops the run) and are skipped for fiction.
- A `real_sourced` channel whose pipeline has no gate stage with `role="research"` **and** one with `role="source_check"` is refused (`GateError`).
- A stage raises a `FrameworkError` (GateError, PipelineError, BudgetError ...) to fail cleanly with a message; the state records it.

## Context helpers

- `ctx.providers["llm"|"image"|"tts"|"music"]` - interfaces in `core/providers/base.py`; call `ctx.charge(kind, result)` to log cost.
- `ctx.costlog.check(project, estimate)` before a paid call (budget cap).
- `ctx.project.path(...)`, `read_json`, `write_json` - files inside the project folder.
- `ctx.rules` - global + channel rules + style learnings text to put in LLM prompts; `ctx.cfg` - the validated config.

## Script format (shared by the bundled pipelines)

`script/script.json`: `{title, hook, lines: [{n, speaker, text, scene, kind, tags}], scenes: [{id, prompt, characters}]}` where `kind` is
`narration | claim | question | arabic | ucharan` (the last two are the surah pipeline's on-screen original text and its reading line) and `tags` are dossier fact IDs.

## Bundled plugins

- `character_story` - research(gate) -> script -> review -> source check(gate) -> images -> TTS -> build -> review -> preview -> upload -> Shorts.
- `surah_explainer` - always `real_sourced`. Inserts the original text from `research/source_text.json` by code and verifies it byte-for-byte; options
  `options.ucharan: true` (needs `research/ucharan.json`). Roles `teacher` / `questioner` expected in `narrators`.

Planned: `narrated_real_story` (long narrated true stories, 10-15 min, with a research dossier per story).

## Providers

Implement `LLMProvider.complete`, `ImageProvider.generate`, `TTSProvider.synthesize` or `MusicProvider.fetch` and point `providers.<kind>.name` at
`package.module:Class` (the class receives the provider config dict). Raise `ProviderUnavailable` on quota/overload so a free-first chain
(`name: "a,b"`) moves on to the next provider.
