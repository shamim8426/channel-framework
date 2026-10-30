# Migrating an existing channel into the framework (guide only)

This is a **checklist for later**; nothing here has been done to any existing channel. The framework never needs the old repo to change:
copy values out, keep the old repo running until the new setup has produced an equivalent dry run.

## 1. Inventory what is hardcoded in the old project
Channel name/handle/ID, characters and their looks, voice IDs and styles, image-style prompts, music files and credits, language-specific strings
(labels, taglines, disclosure lines), tempo and loudness, playlists, category, made_for_kids, publish schedule, forbidden content, per-story budget
rules, folder paths, token locations, agent prompts that name the channel.

## 2. Map each value to config
| Old place | New place |
|---|---|
| channel name, handle, channel ID | `name`, `handle`, `youtube_channel_id` |
| voice IDs / styles | `narrators[]` (+ `characters[].voice_id`) |
| character descriptions | `characters[].description` |
| image-style prompt, negative prompt | `visual_style` |
| music files + credits | `music.tracks[]` (files stay outside git) |
| tempo, LUFS, true peak, music level | `audio` |
| category, kids flag, privacy, playlists, schedule | `youtube.*` |
| Hindi/other on-screen strings | `strings` |
| "never show/say X" | `safety.*` + `rules.md` |
| budget cap | `budget` |
| token / client_secret files | `secrets/<credentials_ref>/` |
| old rules file | channel `rules.md` (global rules live in `RULES.md`) |

## 3. Steps
1. `python -m core new-channel <slug> --pipeline <character_story|surah_explainer>` and copy values from the table.
2. Move `RULES` text into `rules.md`; move earned lessons into `STYLE_LEARNINGS.md`.
3. Put credentials in `secrets/<slug>/` (re-authorize with `python -m core auth`) and set `youtube_channel_id`.
4. `python -m core validate` and `doctor`, then run `start-script` on one old idea with mock providers and compare script structure and upload metadata
   (title, description, tags, category, kids flag, privacy) against the old repo's output for the same idea. Differences should only be intentional.
5. Switch providers one at a time to real ones with `--live`; keep uploads private until the output matches.
6. Import history you want to keep (analytics CSVs, post-mortems) into `channels/<slug>/analytics/` - never into this repo's code.

## 4. Ports still to do (generalize, do not copy channel values)
Depth-based 2.5D camera motion, a per-language burned-in subtitle layer on top of `core/media/text_pil.py`, thumbnail generators, a richer music/ambience
mixer with ducking, stage locks for two machines working on one channel, and a YouTube Analytics provider for `core/analytics.py`.
