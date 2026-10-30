# channel-framework - project instructions

- Engine = `core/`, agent templates = `agents/*.md.tmpl`, global rules = `RULES.md`, channel packs = `channels/<slug>/`. **No channel names, characters,
  voice IDs, style prompts or Hindi/other channel strings in `core/` or `agents/`** (a test enforces it). They belong in `channels/<slug>/channel.yaml`.
- Never commit secrets, tokens, client_secret files, media (mp4/wav/png), story data, analytics or logs. Secrets live in `secrets/<credentials_ref>/` (gitignored).
- No paid API calls and no real uploads in tests or default runs: providers default to `mock`, uploads to dry-run; `--live` is explicit.
- Run `python -m pytest -q` before every commit. Small commits, messages like `<area>: <what changed>`.
- Commands: `python -m core new-channel | start-script | approve | validate | list-channels | doctor | render-agents`.
