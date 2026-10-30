# Global rules (apply to every channel)

Channel `rules.md` files are appended after this file. A channel may add or tighten rules, never loosen one.

## 1. Money and providers
1. **Free first.** For image / voice / music use a free provider first; a paid one only as a fallback, with the reason logged.
2. **Budget.** Every paid call is checked against `budget.hard_cap_per_project` before it runs and written to the channel cost log. Over the cap = stop, simplify the plan.
3. **No surprise spend.** Nothing paid or public happens without `--live`. Default runs use mock providers and dry-run uploads.

## 2. Safety
1. **Secrets** live only in `secrets/<credentials_ref>/` (gitignored) or in environment variables named in the config. Never in config, git, logs, chat or agent prompts.
2. **Channel guard.** Before any upload the authenticated YouTube channel ID must equal `youtube_channel_id`. Mismatch = abort, nothing uploaded.
3. **Private first.** Uploads start `private` unless the owner configured otherwise; the owner publishes after watching.
4. **Forbidden content** configured in `safety.forbidden_depictions` / `forbidden_terms` is enforced in prompts and reviews. A violation is a BLOCKER, not a note.
5. **No imitation.** Never copy another creator's frames, audio, script, characters, title or thumbnail. Study patterns (pace, structure, contrast), not content. Study files are temporary and never committed.
6. **AI disclosure.** Videos with synthetic media say so (`youtube.contains_synthetic_media`, description line from `strings.ai_disclosure`).

## 3. Sourced content (content_type = real_sourced)
1. Research (Khoji) and source check (Munshi) are **mandatory gates**: no dossier, no script; unsourced claim, no upload.
2. Every fact has at least `research.min_sources_per_fact` independent reliable sources and a reliability note. Uncertain = worded as uncertain or dropped.
3. Quoted original text (scripture, laws, documents) is inserted from the supplied source by code and verified byte-for-byte; a model never retypes it.
4. Viral but unsourced or weak stories are listed as "do not use".

## 4. Quality gates (all channels)
1. Every production step is reviewed (PASS / FIX / ASK) before the next one; blockers stop the run.
2. Loudness: target in `audio.target_lufs`, true peak below `audio.true_peak`.
3. Text on screen stays inside safe areas, is large enough to read on a phone, and uses a renderer that shapes the script correctly (Pillow + libraqm for complex scripts).
4. Length and format limits come from `formats.*`; do not pad to reach them.

## 5. Process
1. One stage at a time per channel; stages are idempotent (finished work is cached, re-running resumes).
2. Report what ran, what it cost, and any error in a few lines. Do not hide failures.
3. Small, reviewable commits; never commit media, tokens or story data of another project.
