# Add a channel in 5 minutes

> **Hinglish:** 1) `new-channel` chalao, 2) `rules.md` aur `STYLE_LEARNINGS.md` me apne niyam likho, 3) (live ke liye) YouTube credentials rakho,
> 4) `start-script` se pehli video shuru karo. Bina `--live` ke kuch paid/real nahi hota.

## 1. Create the channel (about 1 minute)

```bash
python -m core new-channel my-channel
```

The wizard asks only: slug, display name, language, niche, pipeline, voice ID(s), one visual-style sentence, YouTube channel ID (Enter to
fill later). Everything else comes from sensible defaults. Non-interactive:

```bash
python -m core new-channel my-channel --yes --name "My Channel" --language en --niche "bedtime stories" \
  --pipeline character_story --voices voice-1 --visual-style "soft watercolour picture book" \
  --forbid-depiction "frightening monsters"
```

It creates `channels/my-channel/` (`channel.yaml`, `rules.md`, `STYLE_LEARNINGS.md`, `characters/`, `music/`, `branding/`, `projects/`),
renders the agents into `.claude/agents/`, and prints **READY FOR SCRIPT** (or the list of what is missing).

Pick the pipeline by what you make: `character_story` (a cast tells a story) or `surah_explainer` (sourced scripture explainer; needs
`content_type: real_sourced`). `content_type: real_sourced` makes research and source-check mandatory for any pipeline.

## 2. Make it yours (2 minutes)

Edit `channels/my-channel/channel.yaml` (see `channels/_template/channel.yaml` for every key):

- `narrators` / `characters` (fixed visual descriptions reused in every image prompt) and their `voice_id`s.
- `visual_style.prompt`, `safety.forbidden_depictions` / `forbidden_terms` (enforced in prompts and reviews).
- `formats` (lengths, script words, Shorts), `audio` (loudness, tempo), `youtube` (category, made_for_kids, privacy, playlists, schedule).
- `providers`: start with `mock`. For real ones: `{name: gemini, model: <model>, api_key_env: GEMINI_API_KEY}`; free-first chain:
  `{name: "cloudflare,gemini", ...}`. Set the env var named in `api_key_env` (never the key itself in config).

Write channel rules in `rules.md` (appended after the global `RULES.md`; may tighten, never loosen) and keep `STYLE_LEARNINGS.md` short and evidence-based.

```bash
python -m core validate --channel my-channel     # readable errors, READY FOR SCRIPT
```

## 3. YouTube credentials (only for live uploads/analytics)

1. Create an OAuth client (Desktop app) in your Google Cloud project; save it as `secrets/my-channel/client_secret.json`.
2. `pip install -r requirements-youtube.txt`, then `python -m core auth --channel my-channel` and log in **with the channel you configured**.
3. Put the real channel ID in `youtube_channel_id`. The framework aborts any upload when the authenticated channel differs.

`secrets/` is gitignored; `python -m core doctor` warns if a secret file is tracked by git. Config only ever holds `credentials_ref` (the folder name).

## 4. Start the first script (the single entry point)

```bash
python -m core start-script --channel my-channel "the topic or story idea"
```

Runs: research (gate, if real_sourced) -> script -> script review -> source check (gate) -> images -> voice -> build -> build review -> **PREVIEW**.
It stops there and waits for you. Read `projects/<NNN>_<slug>/PREVIEW.md`, watch the preview, then:

```bash
python -m core approve --channel my-channel --project 001_the-topic
```

Without `--live` this is a dry run (mock providers, no real upload). With `--live` it uses the configured providers and uploads **private**;
you publish in Studio (or set `youtube.auto_publish: true` to let the framework set `publishAt`). Re-running `start-script --project <name>`
resumes: finished stages are skipped, so a failure never costs you the stages already paid for.

## For real_sourced channels

Put the agent/human research into `projects/<name>/research/dossier.json` (`facts` with at least `research.min_sources_per_fact` distinct sources each) or let
the pipeline draft one. A thin dossier, an untagged claim, or (surah_explainer) original text that differs from `research/source_text.json` stops the run before upload.

## Keep the channel in its own repo (recommended for real channels)

Channels created inside this checkout are fine for trying things out, but a real channel's projects (scripts, dossiers, reviews) should not be
committed to the framework. Put the channel in its own repo and point the framework at it with `--root` (or `CF_ROOT`):

```
some-folder/
  channel-framework/   <- this repo (engine)
  my-channel/          <- your channel repo: channels/my-channel/, secrets/, .claude/agents/
```

```bash
cd channel-framework
python -m core --root ../my-channel new-channel my-channel
python -m core --root ../my-channel start-script --channel my-channel "first idea"
```

Every hint the framework prints (next command, approve line in `PREVIEW.md`) already includes `--root`, and the rendered agents point at
this repo's `RULES.md` with a path relative to the channel repo. A small wrapper script in the channel repo (`cd <framework> && python -m
core --root <channel repo> "$@"`) saves typing.
