"""Stage implementations shared by the bundled pipelines (script review, images, TTS, build, review, preview, upload, shorts).
Everything channel-specific is read from ctx.cfg (channel.yaml); nothing is hardcoded."""
import datetime as dt
import json

from ..analytics import on_upload
from ..errors import GateError, PipelineError
from ..gates import _json_text, find_forbidden
from ..media import ffmpeg as FF
from ..media import text_pil
from .. import publish_slot, youtube
from .base import Context


# ---- script ---------------------------------------------------------------------------------------------------------
def characters_block(cfg) -> str:
    return "\n".join(f"- {c['id']} ({c['name']}): {c['description']}" for c in cfg["characters"]) or "(no fixed characters)"


def speakers(cfg) -> list:
    return [n["id"] for n in cfg["narrators"]] + [c["id"] for c in cfg["characters"] if c.get("voice_id")]


def ask_script(ctx: Context, task: str, header_extra: str = "", dossier: dict | None = None) -> dict:
    lo, hi = ctx.cfg["formats"]["long"]["script_words"]
    header = f"TASK: {task}\nIDEA: {ctx.idea}\nWORDS: {lo}-{hi}\nSPEAKERS: {','.join(speakers(ctx.cfg))}\n{header_extra}"
    body = (f"\nWrite the script as JSON {{title, hook, lines:[{{n, speaker, text, scene, kind, tags}}], scenes:[{{id, prompt, characters}}]}}."
            f"\nkind is one of narration|claim|question|arabic|ucharan; every 'claim' line carries tags (fact ids)."
            f"\nLanguage: {ctx.cfg['language']}. Niche: {ctx.cfg['niche']}.\nCharacters:\n{characters_block(ctx.cfg)}\n"
            f"Visual style: {ctx.cfg['visual_style']['prompt']}\n")
    if dossier:
        body += "\nFACTS (only these may be stated as facts):\n" + "\n".join(f"[{f['id']}] {f['claim']}" for f in dossier["facts"]) + "\n"
    res = ctx.providers["llm"].complete(header + body + "\n" + ctx.rules)
    ctx.charge("llm", res, task)
    data = json.loads(_json_text(res.meta["text"]))
    for l in data["lines"]:
        l.setdefault("kind", "narration")
        l.setdefault("tags", [])
    return data


def write_script(ctx: Context, data: dict):
    ctx.project.write_json("script", "script.json", data=data)
    md = [f"# {data['title']}", "", f"Hook: {data.get('hook', '')}", ""]
    md += [f"{l['n']}. {l['speaker'].upper()} [{l['kind']}]{' ' + str(l['tags']) if l['tags'] else ''}: {l['text']}" for l in data["lines"]]
    ctx.project.path("script", "script.md").write_text("\n".join(md) + "\n", encoding="utf-8")


def stage_review_script(ctx: Context):
    """Munshi-style review: structure, speakers, length, forbidden terms. Failing = stop (fix the script, re-run)."""
    s = ctx.project.read_json("script", "script.json")
    problems, ok_speakers = [], set(speakers(ctx.cfg))
    spoken = [l for l in s["lines"] if l["kind"] != "arabic"]
    words = sum(len(l["text"].split()) for l in spoken)
    lo, hi = ctx.cfg["formats"]["long"]["script_words"]
    if not lo <= words <= hi:
        problems.append(f"length: {words} spoken words, expected {lo}-{hi} (formats.long.script_words)")
    problems += [f"line {l['n']}: unknown speaker '{l['speaker']}'" for l in spoken if l["speaker"] not in ok_speakers]
    bad = find_forbidden(" ".join(l["text"] for l in s["lines"]), ctx.cfg["safety"]["forbidden_terms"])
    problems += [f"forbidden term in script: '{t}'" for t in bad]
    if not s.get("hook"):
        problems.append("no hook")
    rep = ["# script review", "", f"spoken words: {words}"] + ([f"- FAIL {p}" for p in problems] or ["- PASS"])
    ctx.project.path("review", "script_review.md").write_text("\n".join(rep) + "\n", encoding="utf-8")
    if problems:
        raise PipelineError("script review FAILED:\n  - " + "\n  - ".join(problems))
    return {"note": f"{words} words, {len(s['lines'])} lines"}


# ---- images ---------------------------------------------------------------------------------------------------------
def image_prompt(cfg, scene: dict) -> str:
    chars = [c for c in cfg["characters"] if c["id"] in scene.get("characters", [])]
    parts = [cfg["visual_style"]["prompt"], scene["prompt"]] + [f"{c['name']}: {c['description']}" for c in chars]
    never = cfg["safety"]["forbidden_depictions"]
    if never:
        parts.append("Never depict: " + "; ".join(never) + ".")
    if cfg["visual_style"].get("negative_prompt"):
        parts.append("Avoid: " + cfg["visual_style"]["negative_prompt"])
    return " ".join(parts)


def stage_images(ctx: Context):
    s = ctx.project.read_json("script", "script.json")
    scenes = s["scenes"][: ctx.cfg["formats"]["long"]["max_images"]]
    made = 0
    for sc in scenes:
        out = ctx.project.path("images", f"scene_{int(sc['id']):02d}.png")
        if out.exists():
            continue
        prompt = image_prompt(ctx.cfg, sc)
        bad = find_forbidden(sc["prompt"], ctx.cfg["safety"]["forbidden_terms"])
        if bad:
            raise GateError(f"image prompt for scene {sc['id']} contains forbidden term(s): {bad}")
        ctx.costlog.check(ctx.project.name, getattr(ctx.providers["image"], "est_cost", 0.0))
        res = ctx.providers["image"].generate(prompt, out)
        ctx.charge("image", res, f"scene {sc['id']}")
        made += 1
    return {"note": f"{len(scenes)} scenes ({made} generated, rest cached)"}


# ---- voice ----------------------------------------------------------------------------------------------------------
def voice_for(cfg, speaker: str):
    for n in cfg["narrators"]:
        if n["id"] == speaker:
            return n["voice_id"], n.get("style", "")
    for c in cfg["characters"]:
        if c["id"] == speaker and c.get("voice_id"):
            return c["voice_id"], ""
    raise PipelineError(f"no voice for speaker '{speaker}'")


def stage_tts(ctx: Context):
    s = ctx.project.read_json("script", "script.json")
    files, lines = [], [l for l in s["lines"] if l["kind"] != "arabic"]
    for l in lines:
        out = ctx.project.path("audio", "lines", f"{int(l['n']):03d}_{l['speaker']}.wav")
        if not out.exists():
            voice, style = voice_for(ctx.cfg, l["speaker"])
            ctx.costlog.check(ctx.project.name, getattr(ctx.providers["tts"], "est_cost", 0.0))
            res = ctx.providers["tts"].synthesize(l["text"], voice, out, style)
            ctx.charge("tts", res, f"line {l['n']}")
        files.append(out)
    raw = ctx.project.path("audio", "voice_raw.wav")
    spans = FF.concat_wavs(files, raw)
    FF.tempo(raw, ctx.project.path("audio", "voice.wav"), ctx.cfg["audio"]["tempo"])
    factor = ctx.cfg["audio"]["tempo"] or 1.0
    ctx.project.write_json("audio", "timeline.json", data={"lines": [
        {"n": l["n"], "speaker": l["speaker"], "start": round(a / factor, 3), "end": round(b / factor, 3)}
        for l, (a, b) in zip(lines, spans)]})
    return {"note": f"{len(lines)} lines voiced"}


# ---- build ----------------------------------------------------------------------------------------------------------
def title_card(ctx: Context, title: str, path):
    from PIL import Image
    base = Image.new("RGB", (1280, 720), (18, 24, 38))
    sprite = text_pil.render(title, ctx.cfg["options"].get("title_font"), 56, maxw=1100, max_lines=3, box=(0, 0, 0, 0.35), radius=18)
    base.paste(sprite, ((1280 - sprite.width) // 2, (720 - sprite.height) // 2), sprite)
    base.save(path)


def stage_build(ctx: Context):
    s = ctx.project.read_json("script", "script.json")
    tl = ctx.project.read_json("audio", "timeline.json")
    starts = {l["n"]: l for l in tl["lines"]}
    scene_start = {}
    for l in s["lines"]:
        if l["n"] in starts:
            scene_start.setdefault(l["scene"], starts[l["n"]]["start"])
    total = tl["lines"][-1]["end"] + 1.0
    ids = [sid for sid in sorted(scene_start) if ctx.project.path("images", f"scene_{int(sid):02d}.png").exists()]  # capped by max_images
    if not ids:
        raise PipelineError("build: no scene images found")
    images, durs = [], []
    card = ctx.project.path("build", "title_card.png")
    title_card(ctx, s["title"], card)
    images.append(card), durs.append(max(0.5, scene_start[ids[0]]) if ids else 1.0)
    for i, sid in enumerate(ids):
        end = scene_start[ids[i + 1]] if i + 1 < len(ids) else total
        images.append(ctx.project.path("images", f"scene_{int(sid):02d}.png")), durs.append(max(0.5, end - scene_start[sid]))
    manifest = {"images": [str(i) for i in images], "durations": [round(d, 3) for d in durs], "audio": "audio/voice.wav",
                "length_seconds": round(sum(durs), 2)}
    ctx.project.write_json("build", "preview_manifest.json", data=manifest)
    if not FF.have_ffmpeg():
        return {"note": "ffmpeg missing: wrote preview_manifest.json only"}
    raw = ctx.project.path("build", "preview_raw.mp4")
    FF.slideshow(images, durs, ctx.project.path("audio", "voice.wav"), raw)
    out = ctx.project.path("build", "preview.mp4")
    FF.normalize(raw, out, ctx.cfg["audio"]["target_lufs"], ctx.cfg["audio"]["true_peak"])
    raw.unlink(missing_ok=True)
    return {"note": f"preview.mp4 {FF.duration(out):.1f}s"}


def stage_review_build(ctx: Context):
    m = ctx.project.read_json("build", "preview_manifest.json")
    f = ctx.cfg["formats"]["long"]
    problems = []
    if m["length_seconds"] > f["max_seconds"]:
        problems.append(f"too long: {m['length_seconds']}s > max {f['max_seconds']}s")
    if m["length_seconds"] < f["min_seconds"]:
        problems.append(f"too short: {m['length_seconds']}s < min {f['min_seconds']}s")
    video = ctx.project.dir / "build" / "preview.mp4"
    lufs = None
    if video.exists():
        lufs = FF.measure_lufs(video)
        if lufs is not None and abs(lufs - ctx.cfg["audio"]["target_lufs"]) > 2.5:
            problems.append(f"loudness {lufs} LUFS is far from target {ctx.cfg['audio']['target_lufs']}")
    rep = ["# build review", "", f"length {m['length_seconds']}s", f"loudness {lufs}"] + ([f"- FAIL {p}" for p in problems] or ["- PASS"])
    ctx.project.path("review", "build_review.md").write_text("\n".join(rep) + "\n", encoding="utf-8")
    if problems:
        raise PipelineError("build review FAILED:\n  - " + "\n  - ".join(problems))
    return {"note": "ok"}


def stage_preview(ctx: Context):  # approval stage has no fn; this writes the summary BEFORE it (see pipelines)
    s = ctx.project.read_json("script", "script.json")
    md = [f"# PREVIEW for approval: {s['title']}", "", f"channel: {ctx.cfg.name} ({ctx.cfg.slug})", f"project: {ctx.project.name}", "",
          "Files:", "- script/script.md", "- build/preview.mp4 (or build/preview_manifest.json)", "- review/*.md", "",
          "Approve (uploads per channel config, privacy 'private' by default):",
          f"    python -m core approve --channel {ctx.cfg.slug} --project {ctx.project.name}", ""]
    ctx.project.path("PREVIEW.md").write_text("\n".join(md), encoding="utf-8")
    return {"note": "PREVIEW.md written"}


# ---- upload / shorts ------------------------------------------------------------------------------------------------
def taken_days(ctx: Context) -> set:
    f = ctx.ws.channel_dir(ctx.cfg.slug) / "analytics" / "uploads.jsonl"
    tz = publish_slot.ZoneInfo(ctx.cfg["youtube"]["schedule"]["timezone"])
    out = set()
    if f.exists():
        for r in map(json.loads, f.read_text().splitlines()):
            if r.get("kind") == "long" and r.get("planned_slot"):
                out.add(dt.datetime.fromisoformat(r["planned_slot"]["at_utc"]).astimezone(tz).date())
    return out


def description(ctx: Context, s: dict) -> str:
    d = ctx.project.read_json("research", "dossier.json")
    parts = [s.get("hook", ""), ""]
    if d:
        parts += ["Sources:"] + [f"- [{f['id']}] " + "; ".join(x.get("title", "") + " " + x.get("ref", "") for x in f["sources"]) for f in d["facts"]]
        parts.append("")
    parts.append(ctx.cfg["strings"].get("ai_disclosure", "Images and voices are AI-generated."))
    return "\n".join(parts)


def stage_upload(ctx: Context):
    s = ctx.project.read_json("script", "script.json")
    video = ctx.project.dir / "build" / ("preview.mp4" if (ctx.project.dir / "build" / "preview.mp4").exists() else "preview_manifest.json")
    sched = ctx.cfg["youtube"]["schedule"]
    slot = publish_slot.plan_long(sched, ctx.now, taken_days(ctx))
    api = youtube.make_client(ctx.cfg, ctx.ws, ctx.live)
    job = youtube.build_job(ctx.cfg, video, "long", s["title"], description(ctx, s), slot=slot)
    result = youtube.upload(ctx.cfg, api, job, live=ctx.live)
    youtube.save_result(ctx.project.path("output", "upload_result.json"), result)
    on_upload(ctx.ws, ctx.cfg, result, ctx.project.name)
    ctx.project.write_json("output", "_long_slot.json", data={"action": slot.action, "at_utc": slot.at.isoformat()})
    return {"note": f"uploaded {result['video_id']} ({result['privacy']}){' [DRY RUN]' if result['dry_run'] else ''}"}


def stage_shorts(ctx: Context):
    f = ctx.cfg["formats"].get("shorts", {})
    s = ctx.project.read_json("script", "script.json")
    long_slot = ctx.project.read_json("output", "_long_slot.json")
    slot0 = publish_slot.Slot(long_slot["action"], dt.datetime.fromisoformat(long_slot["at_utc"]))
    api = youtube.make_client(ctx.cfg, ctx.ws, ctx.live)
    done = []
    src = ctx.project.dir / "build" / "preview.mp4"
    for k in range(1, f.get("count", 1) + 1):
        out = ctx.project.path("shorts", f"short_{k:02d}.mp4")
        if FF.have_ffmpeg() and src.exists():
            FF.cut_vertical(src, out, 0.0, min(f["max_seconds"], FF.duration(src)))
            video = out
        else:
            ctx.project.write_json("shorts", f"short_{k:02d}.json", data={"source": "build/preview.mp4", "start": 0, "max_seconds": f["max_seconds"]})
            video = ctx.project.dir / "shorts" / f"short_{k:02d}.json"
        job = youtube.build_job(ctx.cfg, video, "short", s["title"] + " #shorts", description(ctx, s),
                                slot=publish_slot.plan_short(ctx.cfg["youtube"]["schedule"], slot0))
        res = youtube.upload(ctx.cfg, api, job, live=ctx.live)
        youtube.save_result(ctx.project.path("shorts", f"short_{k:02d}_result.json"), res)
        on_upload(ctx.ws, ctx.cfg, res, ctx.project.name)
        done.append(res["video_id"])
    return {"note": f"{len(done)} short(s): {', '.join(done)}"}
