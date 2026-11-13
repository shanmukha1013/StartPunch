"""Section generation with retrieved context + response validation."""
from __future__ import annotations

import json
import logging
import re

from .. import llm
from ..ingest.taxonomy import sector_label
from .sections import GROUPS, SECTIONS, section_schema

logger = logging.getLogger("startpunch.generate")

SYSTEM = """You are StartPunch, a rigorous startup research analyst writing one part of a decision-grade report.
Rules:
1. Be specific to THIS idea. No generic filler, no hype words.
2. Evidence: you may cite only the source ids listed under EVIDENCE (e.g. [S3]) in a point's `sources`, and only when the
   snippet actually supports that point. Never invent companies, sources, URLs, user counts, funding amounts or dates.
3. Statements about a named company must come from its evidence snippet; otherwise write 'unknown'.
4. basis: fact = supported by cited evidence; founder_input = taken from the founder's description; estimate = a number
   you derived (state the method/assumptions in the text or `note`); assumption = an unverified premise;
   recommendation = advice. Market sizes, prices, costs and projections are ALWAYS estimate or assumption.
5. Use the founder's geography and currency; if none is given assume USD and say so.
6. When data is missing, say what is missing in `missing` instead of guessing.
   Statements about the evidence itself (e.g. "no direct competitor appears in the retrieved evidence") use basis
   'assumption', never 'fact'.
7. Keep `summary` to 2-4 sentences and each point to one or two sentences. Use empty arrays/tables when not needed.
"""


def build_context(data, signals: dict, classification: dict, evidence: dict, scores: dict | None) -> str:
    sector = (classification.get("sector") or {}).get("top") or []
    model = (classification.get("business_model") or {}).get("top") or []
    lines = ["FOUNDER INPUT (verbatim):", data.as_text(), "",
             "EXTRACTED SIGNALS:", json.dumps({k: signals.get(k) for k in (
                 "one_liner", "customer_type", "buyer", "problem_frequency", "problem_cost", "revenue_model", "price_point",
                 "technical_complexity", "regulated_domains", "capital_intensity", "geography")}, ensure_ascii=False), ""]
    if sector:
        lines.append("ML CLASSIFICATION (predicted, not ground truth): sector = "
                     + ", ".join(f"{sector_label(t['label'])} ({t['probability']:.0%})" for t in sector)
                     + ("; business model = " + ", ".join(f"{t['label']} ({t['probability']:.0%})" for t in model) if model else ""))
    stats = evidence.get("sector_stats")
    if stats:
        trend = stats.get("launch_share_trend", {})
        lines.append(f"KNOWLEDGE-BASE STATS for {stats['label']}: {stats['entities']} entities, "
                     f"{stats['shutdown_announcements']} verified shutdown announcements, launch-share trend {trend.get('direction')} "
                     f"({trend.get('prior_count')} -> {trend.get('recent_count')} launch posts). Coverage: Hacker News only.")
    if scores:
        lines.append(f"RUBRIC SCORE (rule-based): {scores['overall']}/100, confidence {scores['confidence']}. Weakest dimensions: "
                     + ", ".join(f"{d['label']} {d['score']}" for d in sorted(scores['dimensions'], key=lambda d: d['score'])[:3]))
    lines += ["", "EVIDENCE (cite by id; relation was graded against this idea):"]
    for s in evidence.get("sources", []):
        status = " [SHUTDOWN ANNOUNCED]" if s.get("status") == "shutdown_announced" else ""
        lines.append(f"[{s['sid']}] {s['name']}{status} — {s['relation'].replace('_', ' ')}; {s.get('stream')} {s.get('date') or ''}\n"
                     f"     {s.get('title') or ''}: {s['snippet'][:420]}")
    if not evidence.get("sources"):
        lines.append("(no relevant evidence retrieved — say so where it matters)")
    if evidence.get("recent_launches"):
        lines.append("RECENT LAUNCHES IN SECTOR (last 24 months, names only): "
                     + "; ".join(f"{r['name']} ({r['date']})" for r in evidence["recent_launches"][:6]))
    return "\n".join(lines)


def write_group(group: str, context: str, deadline: float | None = None) -> dict:
    keys = GROUPS[group]
    guidance = "\n".join(f"- {k} — {SECTIONS[k][0]}: {SECTIONS[k][2]}" for k in keys)
    prompt = f"{context}\n\nWRITE THESE SECTIONS (one object per key, in order):\n{guidance}"
    result = llm.generate_json(prompt, system=SYSTEM, schema=section_schema(keys), temperature=0.35,
                               max_output_tokens=12000, timeout=50, deadline=deadline)
    sections = {}
    for item in (result.data or {}).get("sections", []):
        if isinstance(item, dict) and item.get("key") in keys:
            sections[item["key"]] = item
    return {"sections": sections, "model": result.model, "latency_ms": result.latency_ms,
            "tokens": {"in": result.input_tokens, "out": result.output_tokens}}


def write_synthesis(context: str, sections: dict, scores: dict, deadline: float | None = None) -> dict:
    digest = "\n".join(f"- {SECTIONS[k][0]}: {s.get('summary', '')[:400]}" for k, s in sections.items() if k in SECTIONS)
    keys = GROUPS["synthesis"]
    guidance = "\n".join(f"- {k} — {SECTIONS[k][0]}: {SECTIONS[k][2]}" for k in keys)
    prompt = (f"{context}\n\nSECTION SUMMARIES ALREADY WRITTEN:\n{digest}\n\nOverall rubric score {scores['overall']}/100 "
              f"(confidence {scores['confidence']}).\n\nWRITE THESE SECTIONS:\n{guidance}")
    result = llm.generate_json(prompt, system=SYSTEM, schema=section_schema(keys), temperature=0.3, max_output_tokens=5000,
                               timeout=45, deadline=deadline)
    out = {item["key"]: item for item in (result.data or {}).get("sections", []) if isinstance(item, dict) and item.get("key") in keys}
    return {"sections": out, "model": result.model}


# ------------------------------------------------------------------------------ validation
_NUMBER = re.compile(r"(?<![\w.])(?:\$|€|£|₹)?\d[\d,.]*(?:\s?(?:%|k|m|bn|b|million|billion|crore|lakh))?", re.I)


def _norm(text: str) -> str:
    return re.sub(r"\s+", " ", (text or "").lower())


def validate(sections: dict, evidence: dict) -> tuple[dict, dict]:
    """Check citations against the evidence set; downgrade unsupported 'facts'. Returns (sections, report)."""
    by_sid = {s["sid"]: s for s in evidence.get("sources", [])}
    names = {s["name"].lower(): s["sid"] for s in evidence.get("sources", []) if len(s["name"]) > 2}
    report = {"citations_checked": 0, "citations_removed": 0, "facts_downgraded": 0, "facts_supported": 0,
              "metrics_relabelled": 0, "notes": []}
    for key, section in sections.items():
        for point in section.get("points", []):
            raw = [str(s).strip().strip("[]") for s in point.get("sources", [])]
            valid = [s for s in raw if s in by_sid]
            report["citations_checked"] += len(raw)
            report["citations_removed"] += len(raw) - len(valid)
            point["sources"] = list(dict.fromkeys(valid))
            text = point.get("text", "")
            # Inline [S#] markers must also be valid.
            for marker in set(re.findall(r"\[(S\d+)\]", text)):
                if marker not in by_sid:
                    text = text.replace(f"[{marker}]", "")
                    report["citations_removed"] += 1
                elif marker not in point["sources"]:
                    point["sources"].append(marker)
            point["text"] = text.strip()
            if point.get("basis") == "fact":
                support = _norm(" ".join(f"{by_sid[s]['name']} {by_sid[s]['title']} {by_sid[s]['snippet']} {by_sid[s].get('date') or ''}"
                                         for s in point["sources"]))
                problems = []
                if not point["sources"]:
                    problems.append("no valid source")
                else:
                    for num in _NUMBER.findall(text):
                        digits = re.sub(r"[^\d]", "", num)
                        material = bool(re.search(r"[$€£₹%]|k|m|bn|b|million|billion|crore|lakh", num, re.I))
                        if (material or len(digits) >= 2) and digits not in re.sub(r"[^\d ]", "", support):
                            problems.append(f"number '{num.strip()}' not in cited evidence")
                            break
                    for name, sid in names.items():
                        if re.search(rf"\b{re.escape(name)}\b", text.lower()) and sid not in point["sources"]:
                            problems.append(f"mentions {name} without citing it")
                            break
                if problems:
                    point["basis"] = "unverified"
                    point["validation"] = problems
                    report["facts_downgraded"] += 1
                else:
                    point["validation"] = ["supported by cited evidence"]
                    report["facts_supported"] += 1
        for metric in section.get("metrics", []):
            if metric.get("basis") == "fact":
                metric["basis"] = "estimate"  # no metric in this KB can be a sourced fact
                report["metrics_relabelled"] += 1
        table = section.get("table") or {}
        if not table.get("columns"):
            section["table"] = {"columns": [], "rows": []}
        section["title"] = SECTIONS.get(key, (key,))[0]
    return sections, report
