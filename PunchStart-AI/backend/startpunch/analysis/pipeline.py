"""Staged analysis pipeline.

Each call to ``advance(report_id)`` runs exactly one stage and persists its output, so the
pipeline works inside short serverless invocations (and resumes after interruptions):

    understand  -> embed idea, ML classification, LLM signal extraction, cluster assignment
    research    -> hybrid retrieval, LLM relevance grading, evidence bundle, rubric scores
    write       -> 5 section groups generated in parallel (failed groups retried on next call)
    synthesize  -> executive summary + final recommendations, citation validation, finalize

A row-level lease (``lock_until``) prevents two requests from processing the same report.
"""
from __future__ import annotations

import logging
import time
from concurrent.futures import ThreadPoolExecutor
from datetime import timedelta

from sqlalchemy import and_, insert, or_, select, update

from .. import __version__, db, llm
from ..kb.store import get_kb
from ..ml import classifier, clusters
from ..utils import new_id, utcnow
from . import generate, research, scoring, signals as signals_mod
from .sections import GROUPS, SECTION_ORDER, SECTIONS, WRITE_GROUPS
from .signals import AnalysisInput

logger = logging.getLogger("startpunch.pipeline")
ENGINE_VERSION = f"startpunch-{__version__}"
STAGES = ["understand", "research", "write", "synthesize", "complete"]
PROGRESS = {"understand": 5, "research": 25, "write": 45, "synthesize": 85, "complete": 100}
MAX_GROUP_ATTEMPTS = 2
LEASE_SECONDS = 75
STAGE_BUDGET_SECONDS = 52  # keep every stage inside a 60 s serverless invocation


def _acquire(report_id: str) -> bool:
    now = utcnow()
    with db.transaction() as conn:
        result = conn.execute(
            update(db.reports)
            .where(and_(db.reports.c.id == report_id,
                        or_(db.reports.c.lock_until.is_(None), db.reports.c.lock_until < now)))
            .values(lock_until=now + timedelta(seconds=LEASE_SECONDS))
        )
        return result.rowcount == 1


def _save(report_id: str, **values) -> None:
    values["updated_at"] = utcnow()
    with db.transaction() as conn:
        conn.execute(update(db.reports).where(db.reports.c.id == report_id).values(**values))


def _stage_understand(data: AnalysisInput, state: dict) -> dict:
    embedding = None
    if llm.available():
        try:
            embedding = llm.embed_query(data.search_text())
        except llm.LLMUnavailable as exc:
            logger.warning("idea embedding unavailable: %s", exc)
    text = data.search_text()
    classification = {
        "sector": classifier.predict("industry", text, embedding),
        "business_model": classifier.predict("business_model", text, embedding),
        "cluster": clusters.assign(embedding),
    }
    sig = signals_mod.extract(data) if llm.available() else signals_mod.heuristic(data)
    state.update(signals=sig, classification=classification, idea_embedding=embedding)
    return state


def _stage_research(data: AnalysisInput, state: dict) -> dict:
    evidence = research.run(data, state["signals"], state["classification"], state.get("idea_embedding"))
    state["evidence"] = evidence
    state["scores"] = scoring.score(state["signals"], data, evidence)
    state.pop("idea_embedding", None)  # not needed any more; keep rows small
    return state


def _stage_write(data: AnalysisInput, state: dict) -> tuple[dict, bool]:
    context = generate.build_context(data, state["signals"], state["classification"], state["evidence"], state["scores"])
    groups = state.setdefault("groups", {})
    todo = [g for g in WRITE_GROUPS if groups.get(g, {}).get("status") != "done"
            and groups.get(g, {}).get("attempts", 0) < MAX_GROUP_ATTEMPTS]

    deadline = time.time() + STAGE_BUDGET_SECONDS

    def run(group: str):
        try:
            return group, generate.write_group(group, context, deadline=deadline), None
        except llm.LLMUnavailable as exc:
            return group, None, str(exc)[:300]

    with ThreadPoolExecutor(max_workers=len(todo) or 1) as pool:
        for group, output, error in pool.map(run, todo):
            entry = groups.setdefault(group, {"attempts": 0})
            entry["attempts"] = entry.get("attempts", 0) + 1
            if output and output["sections"]:
                entry.update(status="done", sections=output["sections"], model=output["model"],
                             latency_ms=output["latency_ms"], tokens=output["tokens"],
                             missing=[k for k in GROUPS[group] if k not in output["sections"]])
            else:
                entry.update(status="failed", error=error or "empty response")
    finished = all(groups.get(g, {}).get("status") == "done" or groups.get(g, {}).get("attempts", 0) >= MAX_GROUP_ATTEMPTS
                   for g in WRITE_GROUPS)
    return state, finished


def _stage_synthesize(data: AnalysisInput, state: dict) -> tuple[dict, dict]:
    sections: dict = {}
    models_used = set()
    for group in WRITE_GROUPS:
        entry = state.get("groups", {}).get(group, {})
        sections.update(entry.get("sections") or {})
        if entry.get("model"):
            models_used.add(entry["model"])
    synthesis_error = None
    if sections:
        context = generate.build_context(data, state["signals"], state["classification"], state["evidence"], state["scores"])
        try:
            synth = generate.write_synthesis(context, sections, state["scores"], deadline=time.time() + STAGE_BUDGET_SECONDS)
            sections.update(synth["sections"])
            models_used.add(synth["model"])
        except llm.LLMUnavailable as exc:
            synthesis_error = str(exc)[:300]
    sections, validation = generate.validate(sections, state["evidence"])
    unavailable = [k for k in SECTION_ORDER if k not in sections]
    reason = ("The AI engine is not configured on this server." if not llm.available()
              else "The AI engine did not return this section (quota or timeout). Re-run the analysis later.")
    for key in unavailable:
        sections[key] = {"key": key, "title": SECTIONS[key][0], "unavailable": True, "summary": reason, "points": [],
                         "metrics": [], "groups": [], "table": {"columns": [], "rows": []}, "missing": [], "confidence": "low"}
    validation["sections_unavailable"] = unavailable
    if synthesis_error:
        validation["notes"].append(f"Synthesis failed: {synthesis_error}")
    kb = get_kb()
    result = {
        "engine": {
            "version": ENGINE_VERSION, "rubric": scoring.RUBRIC_VERSION, "llm_models": sorted(models_used),
            "signals_model": state["signals"].get("model"), "embedding_model": "gemini-embedding-001",
            "classifiers": {k: (v or {}).get("model") for k, v in state["classification"].items() if k != "cluster"},
            "cluster_model": (state["classification"].get("cluster") or {}).get("model"),
            "kb_snapshot": (kb.manifest or {}).get("snapshot_id"),
            "retrieval_mode": state["evidence"]["retrieval"].get("mode"),
        },
        "title": data.display_name(),
        "signals": state["signals"],
        "classification": state["classification"],
        "evidence": state["evidence"],
        "scores": state["scores"],
        "sections": sections,
        "section_order": SECTION_ORDER,
        "validation": validation,
        "generated_at": utcnow().isoformat(),
    }
    return state, result


def _seed_validation_items(conn, report_id: str, user_id: str, result: dict) -> None:
    section = result["sections"].get("validation_experiments") or {}
    table = section.get("table") or {}
    columns = [c.lower() for c in table.get("columns", [])]
    now = utcnow()

    def col(row, *names):
        for name in names:
            for i, column in enumerate(columns):
                if name in column and i < len(row):
                    return row[i]
        return ""

    for row in (table.get("rows") or [])[:8]:
        hypothesis = col(row, "hypothesis") or (row[0] if row else "")
        if not hypothesis:
            continue
        conn.execute(insert(db.validation_items).values(
            id=new_id(), report_id=report_id, user_id=user_id, title=hypothesis[:200], hypothesis=hypothesis,
            method=col(row, "experiment", "method"), success_metric=" — ".join(x for x in (col(row, "metric"), col(row, "threshold")) if x),
            status="todo", notes="", created_at=now, updated_at=now))


def advance(report_id: str) -> dict:
    """Run the next stage for a report. Returns the updated status payload."""
    with db.read() as conn:
        row = conn.execute(select(db.reports).where(db.reports.c.id == report_id)).first()
    if row is None:
        raise KeyError(report_id)
    if row.status in {"complete", "failed", "partial"} or row.legacy:
        return status_payload(row)
    if not _acquire(report_id):
        return {**status_payload(row), "busy": True}

    data = AnalysisInput.model_validate(row.input)
    state = dict(row.state or {})
    stage = row.stage
    try:
        if stage == "understand":
            state = _stage_understand(data, state)
            _save(report_id, state=state, stage="research", status="running", progress=PROGRESS["research"], lock_until=None)
        elif stage == "research":
            state = _stage_research(data, state)
            _save(report_id, state=state, stage="write", status="running", progress=PROGRESS["write"], lock_until=None)
        elif stage == "write":
            if not llm.available():
                _save(report_id, state=state, stage="synthesize", progress=PROGRESS["synthesize"], lock_until=None)
            else:
                state, finished = _stage_write(data, state)
                done = sum(1 for g in WRITE_GROUPS if state["groups"].get(g, {}).get("status") == "done")
                progress = PROGRESS["write"] + int((PROGRESS["synthesize"] - PROGRESS["write"]) * done / len(WRITE_GROUPS))
                _save(report_id, state=state, stage="synthesize" if finished else "write",
                      progress=PROGRESS["synthesize"] if finished else progress, lock_until=None)
        elif stage == "synthesize":
            state, result = _stage_synthesize(data, state)
            complete = not result["validation"]["sections_unavailable"]
            now = utcnow()
            with db.transaction() as conn:
                conn.execute(update(db.reports).where(db.reports.c.id == report_id).values(
                    state={"groups_meta": {g: {k: v for k, v in e.items() if k != "sections"} for g, e in state.get("groups", {}).items()}},
                    result=result, stage="complete", status="complete" if complete else "partial", progress=100,
                    completed_at=now, updated_at=now, lock_until=None, engine_version=ENGINE_VERSION))
                _seed_validation_items(conn, report_id, row.user_id, result)
    except Exception as exc:  # unexpected failure: record it honestly, never fabricate a report
        logger.exception("pipeline stage %s failed for %s", stage, report_id)
        _save(report_id, status="failed", error=f"Stage '{stage}' failed: {type(exc).__name__}", lock_until=None)
    with db.read() as conn:
        row = conn.execute(select(db.reports).where(db.reports.c.id == report_id)).first()
    return status_payload(row)


def run_to_completion(report_id: str, max_steps: int = 12) -> dict:
    payload = {}
    for _ in range(max_steps):
        payload = advance(report_id)
        if payload["status"] in {"complete", "failed", "partial"}:
            break
    return payload


STAGE_LABELS = {
    "understand": "Understanding the idea (classification, signal extraction)",
    "research": "Researching the knowledge base (retrieval, relevance grading, scoring)",
    "write": "Writing the report sections",
    "synthesize": "Synthesizing, validating citations",
    "complete": "Complete",
}


def status_payload(row) -> dict:
    state = row.state or {}
    groups = state.get("groups") or state.get("groups_meta") or {}
    return {
        "id": row.id, "status": row.status, "stage": row.stage, "stage_label": STAGE_LABELS.get(row.stage, row.stage),
        "progress": row.progress, "error": row.error,
        "groups": {g: {"status": e.get("status"), "attempts": e.get("attempts")} for g, e in groups.items()},
    }
