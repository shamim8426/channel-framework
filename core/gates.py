"""Mandatory gates for content_type=real_sourced (Khoji-style research, Munshi-style source check) plus shared guards."""
import hashlib
import json

from .errors import GateError
from .pipelines.base import Context


def find_forbidden(text: str, terms) -> list:
    low = text.lower()
    return [t for t in terms if t and t.lower() in low]


def validate_dossier(dossier: dict, min_sources: int):
    facts = dossier.get("facts") or []
    if not facts:
        raise GateError("research gate: dossier has no facts")
    problems = []
    for f in facts:
        refs = {(s.get("title", ""), s.get("ref", "")) for s in f.get("sources", []) if s.get("title") or s.get("ref")}
        if not f.get("id") or not f.get("claim"):
            problems.append(f"fact without id/claim: {f}")
        elif len(refs) < min_sources:
            problems.append(f"{f['id']}: {len(refs)} distinct source(s), need {min_sources}")
    if problems:
        raise GateError("research gate FAILED:\n  - " + "\n  - ".join(problems))


def research_stage(ctx: Context):
    """Khoji gate. Uses research/dossier.json if an agent/human already wrote it; else asks the LLM for a first draft."""
    d = ctx.project.read_json("research", "dossier.json")
    if d is None:
        prompt = f"TASK: research\nIDEA: {ctx.idea}\n\nReturn JSON {{topic, facts:[{{id, claim, sources:[{{title, ref}}]}}]}}. Every fact needs " \
                 f"{ctx.cfg['research']['min_sources_per_fact']}+ independent reliable sources. Mark uncertain facts as such.\n\n{ctx.rules}"
        res = ctx.providers["llm"].complete(prompt)
        ctx.charge("llm", res, "research")
        d = json.loads(_json_text(res.meta["text"]))
        ctx.project.write_json("research", "dossier.json", data=d)
    validate_dossier(d, ctx.cfg["research"]["min_sources_per_fact"])
    return {"note": f"{len(d['facts'])} facts, all with >= {ctx.cfg['research']['min_sources_per_fact']} sources"}


def source_check_stage(ctx: Context):
    """Munshi gate: every 'claim' line carries tags that exist in the dossier; unknown tags or untagged claims fail."""
    d = ctx.project.read_json("research", "dossier.json")
    script = ctx.project.read_json("script", "script.json")
    if d is None or script is None:
        raise GateError("source check: dossier.json or script.json missing")
    ids = {f["id"] for f in d["facts"]}
    problems = []
    for l in script["lines"]:
        if l.get("kind") == "claim":
            tags = l.get("tags") or []
            if not tags:
                problems.append(f"line {l['n']}: claim without a source tag")
            problems += [f"line {l['n']}: tag {t} not in dossier" for t in tags if t not in ids]
    report = ["# source check", ""] + ([f"- FAIL {p}" for p in problems] or ["- PASS: every claim line is tagged and sourced"])
    ctx.project.path("review", "source_check.md").write_text("\n".join(report) + "\n", encoding="utf-8")
    if problems:
        raise GateError("source check FAILED:\n  - " + "\n  - ".join(problems))
    return {"note": "all claims sourced"}


def _json_text(text: str) -> str:
    """Extract the JSON object from an LLM reply (handles ``` fences and chatter)."""
    a, b = text.find("{"), text.rfind("}")
    if a < 0 or b < a:
        raise GateError("LLM reply did not contain a JSON object")
    return text[a:b + 1]


def sha256(text: str) -> str:
    return hashlib.sha256(text.encode("utf-8")).hexdigest()
