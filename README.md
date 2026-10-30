# channel-framework

> **Hinglish note:** Ye ek reusable multi-channel YouTube framework hai. Naya channel banao (`new-channel`), phir seedha script se shuru karo
> (`start-script`). Channel ka naam, kirdaar, awaazein, style, music, YouTube settings sab `channels/<slug>/channel.yaml` me hote hain,
> engine (`core/`) me koi channel ka naam nahi. Default run me koi paid call ya real upload nahi hota (mock providers + dry run); sirf `--live` se hota hai.

A config-driven framework that takes a channel from **script to a private YouTube upload**. Everything channel-specific (name, characters,
voice IDs, visual style, music, language, YouTube defaults, schedule, safety rules) lives in `channels/<slug>/channel.yaml` and
`channels/<slug>/rules.md`. The engine in `core/` and the agent templates in `agents/` contain no channel names.

## Quick start (5 minutes)

```bash
./scripts/setup.sh                      # venv + dependencies + doctor   (Windows: scripts\setup.ps1)
python -m core new-channel my-channel   # wizard: only the essentials -> "READY FOR SCRIPT"
python -m core start-script --channel my-channel "a short idea or topic"
python -m core approve --channel my-channel --project 001_a-short-idea      # after you looked at the preview
```

Try it without creating anything: `python -m core start-script --channel example-story "Pip finds a lost star"` (fully fictional demo channel,
mock providers, dry-run upload).

## What you get

| Piece | Where |
|---|---|
| Config loader + JSON-Schema validation (`channel.yaml` or `channel.json`), readable errors | `core/config.py`, `core/schema/channel.schema.json` |
| Secrets: `secrets/<credentials_ref>/` (gitignored), only references in config | `core/secrets.py` |
| YouTube upload with **channel-ID guard** (abort on mismatch), schedule planner, analytics hooks | `core/youtube.py`, `core/publish_slot.py`, `core/analytics.py` |
| Cost log + per-project budget cap | `core/costlog.py` |
| Providers behind interfaces (LLM, image, TTS, music) + mock for each, free-first fallback chains | `core/providers/` |
| Pipeline plugins: `character_story`, `surah_explainer` (+ your own) | `core/pipelines/`, `docs/PIPELINES.md` |
| `content_type`: `fiction` or `real_sourced` (research + source-check become **mandatory gates**) | `core/gates.py`, `RULES.md` |
| Agent templates (Khoji, Kalam, Munshi, Sampadak, Nigraan, Kaarigar) rendered per channel into `.claude/agents/` | `agents/*.tmpl`, `core/agents.py` |
| Global rules + per-channel rules | `RULES.md`, `channels/<slug>/rules.md` |
| Templates and a demo channel | `channels/_template/`, `channels/example-story/` |

## Commands (`python -m core ...`)

| Command | What it does |
|---|---|
| `new-channel [slug]` | wizard (or flags with `--yes`); fills defaults, validates, renders agents, leaves the channel READY FOR SCRIPT |
| `start-script --channel <slug> "<idea>"` | everything from research/script to a PREVIEW awaiting your approval (`--project <name>` resumes) |
| `approve --channel <slug> --project <name>` | after approval: upload (private by default) + Shorts, guarded by the channel ID |
| `validate --channel <slug>` | config + readiness checklist |
| `list-channels` | all channels with pipeline, content type, readiness |
| `doctor [--channel <slug>]` | Python deps, ffmpeg, RAQM, secrets, API keys, git hygiene |
| `render-agents [--channel <slug>]` | write `.claude/agents/<role>-<slug>.md` |
| `reports --channel <slug>` | which 48 h / 7 d analytics post-mortems are due |
| `auth --channel <slug>` | one-time YouTube OAuth login (live) |

**Safety defaults:** no flag = mock providers + dry-run upload. `--live` is required for real providers and real uploads, and a live
upload needs the real `youtube_channel_id` in the config.

## Tests

```bash
pip install -r requirements.txt
python -m pytest -q          # unit tests + end-to-end dry runs with mock providers (no network, no paid calls)
```

## Docs

- [docs/ADD_A_CHANNEL.md](docs/ADD_A_CHANNEL.md) - add a channel in 5 minutes
- [docs/PIPELINES.md](docs/PIPELINES.md) - the pipeline interface and how to write a plugin
- [docs/MIGRATING_EXISTING_CHANNEL.md](docs/MIGRATING_EXISTING_CHANNEL.md) - moving an existing channel into the framework later

## What is deliberately not here

Media, tokens, `client_secret` files, story data, analytics and logs never go into this repo (see `.gitignore`). The two bundled pipelines
are generalized ports of working channel flows; richer production steps (depth-based camera motion, burned-in subtitles per language,
thumbnail generators) are described in `docs/MIGRATING_EXISTING_CHANNEL.md` as the next ports.
