from .base import Context, Pipeline, Project, Stage, load_pipeline, register, run_pipeline, PIPELINES  # noqa: F401
from . import character_story, surah_explainer  # noqa: F401  (registers the bundled plugins)
