"""AI Founder Assistant: conversational follow-ups grounded in one report + fresh retrieval."""
from __future__ import annotations

import json
import logging
import re

from .. import llm
from ..kb import retrieval
from .sections import SECTIONS

logger = logging.getLogger("startpunch.assistant")

_SCHEMA = llm.obj({
    "answer": llm.S("string"),
    "citations": llm.arr(llm.S("string")),
    "answer_type": llm.enum(["grounded", "scenario", "advice", "insufficient_evidence"]),
    "follow_ups": llm.arr(llm.S("string")),
})

SYSTEM = """You are the StartPunch founder assistant. You help one founder think about THEIR startup report.
- Ground answers in the REPORT and EVIDENCE below. Cite evidence only with ids shown ([S#] from the report, [K#] from fresh
  retrieval) and only where the snippet supports the statement. Never invent companies, numbers, sources or URLs.
- Explain scores using the rubric rationale given; the score is rule-based, not a prediction of success.
- For "what if" questions, reason explicitly about which rubric dimensions and sections would change, and label the
  answer_type 'scenario'.
- If the evidence cannot answer the question, say so plainly (answer_type 'insufficient_evidence') and suggest how to find out.
- Be concise and specific. Use short paragraphs or '- ' bullet lines. No markdown headings.
"""


def _digest(report: dict) -> str:
    scores = report.get("scores", {})
    lines = [f"STARTUP: {report.get('title')}", f"ONE-LINER: {report.get('signals', {}).get('one_liner', '')}",
             f"RUBRIC: {scores.get('overall')}/100 (confidence {scores.get('confidence')}; {scores.get('method', '')})"]
    for dim in scores.get("dimensions", []):
        lines.append(f"  - {dim['label']}: {dim['score']}/10 (weight {dim['weight']}) — {dim['rationale']}")
    lines.append("SECTIONS (summaries):")
    for key in report.get("section_order", []):
        section = report.get("sections", {}).get(key) or {}
        if section.get("unavailable"):
            continue
        lines.append(f"  - {SECTIONS.get(key, (key,))[0]}: {section.get('summary', '')[:350]}")
    lines.append("REPORT EVIDENCE:")
    for source in report.get("evidence", {}).get("sources", [])[:20]:
        status = " [shutdown announced]" if source.get("status") == "shutdown_announced" else ""
        lines.append(f"  [{source['sid']}] {source['name']}{status} ({source['relation']}): {source['snippet'][:240]}")
    return "\n".join(lines)


def answer(report: dict, history: list[dict], question: str) -> dict:
    fresh, _ = retrieval.search([question, f"{report.get('signals', {}).get('one_liner', '')} {question}"], k_companies=6)
    known = {s["sid"]: s for s in report.get("evidence", {}).get("sources", [])}
    known_ids = {s["company_id"] for s in known.values()}
    extra = []
    for hit in fresh:
        if hit["company_id"] in known_ids or not hit["evidence"]:
            continue
        doc = hit["evidence"][0]
        extra.append({"sid": f"K{len(extra) + 1}", "company_id": hit["company_id"], "name": hit["name"], "url": doc["url"],
                      "title": doc.get("title"), "date": doc.get("date"), "snippet": doc["text"][:500],
                      "status": hit.get("status"), "relation": "retrieved for this question"})
    convo = "\n".join(f"{m['role'].upper()}: {m['content'][:1200]}" for m in history[-8:])
    fresh_block = "\n".join(f"  [{e['sid']}] {e['name']}: {e['snippet'][:300]}" for e in extra) or "  (none)"
    prompt = (f"{_digest(report)}\n\nFRESH RETRIEVAL FOR THIS QUESTION:\n{fresh_block}\n\n"
              f"CONVERSATION SO FAR:\n{convo or '(new conversation)'}\n\nFOUNDER: {question}\n\n"
              "Reply with: answer, citations (ids used), answer_type, follow_ups (2-3 short questions the founder might ask next).")
    result = llm.generate_json(prompt, system=SYSTEM, schema=_SCHEMA, temperature=0.4, max_output_tokens=2500, timeout=45)
    data = result.data if isinstance(result.data, dict) else {}
    lookup = {**known, **{e["sid"]: e for e in extra}}
    text = str(data.get("answer", "")).strip()
    cited = [c.strip("[] ") for c in data.get("citations", [])] + re.findall(r"\[([SK]\d+)\]", text)
    valid = [c for c in dict.fromkeys(cited) if c in lookup]
    for marker in set(re.findall(r"\[([SK]\d+)\]", text)) - set(valid):
        text = text.replace(f"[{marker}]", "")
    sources = [{k: lookup[c].get(k) for k in ("sid", "name", "url", "title", "date", "status", "relation")} for c in valid]
    return {
        "answer": text or "I could not produce an answer this time.",
        "answer_type": data.get("answer_type", "advice"),
        "sources": sources,
        "follow_ups": [f for f in data.get("follow_ups", []) if isinstance(f, str)][:3],
        "model": result.model,
        "citations_removed": len(set(cited)) - len(valid),
    }


def export_markdown(report_row: dict) -> str:
    """Plain Markdown export of a report (no HTML), including sources and method notes."""
    result = report_row.get("result") or {}
    scores = result.get("scores", {})
    out = [f"# {result.get('title') or report_row.get('title')}", "",
           f"*Generated {result.get('generated_at', '')[:10]} by StartPunch ({result.get('engine', {}).get('version', '')}).*", "",
           f"**Rubric score:** {scores.get('overall')}/100 — confidence {scores.get('confidence')}. _{scores.get('method', '')}_", ""]
    for dim in scores.get("dimensions", []):
        out.append(f"- **{dim['label']}** {dim['score']}/10 — {dim['rationale']}")
    out.append("")
    basis_label = {"fact": "Fact", "founder_input": "Founder input", "estimate": "Estimate", "assumption": "Assumption",
                   "recommendation": "Recommendation", "unverified": "Unverified AI claim"}
    for key in result.get("section_order", []):
        section = result.get("sections", {}).get(key)
        if not section:
            continue
        out += [f"## {section.get('title', key)}", "", section.get("summary", ""), ""]
        for metric in section.get("metrics", []):
            out.append(f"- **{metric['label']}:** {metric['value']} ({basis_label.get(metric.get('basis'), metric.get('basis'))})"
                       + (f" — {metric['note']}" if metric.get("note") else ""))
        for group in section.get("groups", []):
            out.append(f"**{group['label']}**")
            out += [f"- {item}" for item in group.get("items", [])]
        table = section.get("table") or {}
        if table.get("columns"):
            out.append("| " + " | ".join(table["columns"]) + " |")
            out.append("|" + "---|" * len(table["columns"]))
            out += ["| " + " | ".join(str(c).replace("|", "/") for c in row) + " |" for row in table.get("rows", [])]
        for point in section.get("points", []):
            refs = " ".join(f"[{s}]" for s in point.get("sources", []))
            out.append(f"- {point['text']} _({basis_label.get(point.get('basis'), point.get('basis'))})_ {refs}".rstrip())
        out.append("")
    out += ["## Sources", ""]
    for source in result.get("evidence", {}).get("sources", []):
        out.append(f"- [{source['sid']}] {source['name']} — {source.get('title') or ''} ({source.get('date') or 'n.d.'}) {source.get('url') or ''}")
    out += ["", "_Coverage: " + result.get("evidence", {}).get("knowledge_base", {}).get("coverage_note", "") + "_"]
    return "\n".join(out)


def to_json(report: dict) -> str:
    return json.dumps(report, ensure_ascii=False, indent=2)
