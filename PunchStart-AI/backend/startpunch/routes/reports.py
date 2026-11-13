"""Startup reports: create, run (staged), read, assistant chat, export, validation tracker, watchlist, compare."""
from __future__ import annotations

from typing import Any

from fastapi import APIRouter, Depends, HTTPException, Query, Request
from fastapi.responses import PlainTextResponse, Response
from pydantic import BaseModel, Field
from sqlalchemy import delete, desc, func, insert, select, update

from .. import db, llm, ratelimit
from ..analysis import assistant, clarify as clarify_mod, pipeline
from ..analysis.signals import AnalysisInput
from ..kb.retrieval import company_card
from ..security import CurrentUser, current_user
from ..utils import clean_text, iso, new_id, utcnow

router = APIRouter(tags=["reports"])


def _own_report(conn, report_id: str, user_id: str):
    row = conn.execute(select(db.reports).where(db.reports.c.id == report_id)).first()
    if row is None or row.user_id != user_id:
        raise HTTPException(404, "Report not found.")
    return row


def _summary(row) -> dict:
    result = row.result or {}
    scores = result.get("scores") or {}
    classification = result.get("classification") or {}
    sector = ((classification.get("sector") or {}).get("top") or [{}])[0]
    return {
        "id": row.id, "title": row.title, "status": row.status, "stage": row.stage, "progress": row.progress,
        "legacy": row.legacy, "score": scores.get("overall") if not row.legacy else result.get("legacy_score"),
        "confidence": scores.get("confidence"), "sector": sector.get("label"),
        "one_liner": (result.get("signals") or {}).get("one_liner") or (row.input or {}).get("idea", "")[:160],
        "created_at": iso(row.created_at), "completed_at": iso(row.completed_at),
    }


# ----------------------------------------------------------------------------- clarify
@router.post("/analysis/clarify")
def clarify(payload: AnalysisInput, user: CurrentUser = Depends(current_user)):
    ratelimit.hit("ai", user.id)
    if llm.available():
        ratelimit.consume_ai_quota(user.id, "clarify")
    return clarify_mod.clarify(payload)


# ----------------------------------------------------------------------------- reports
@router.post("/reports", status_code=201)
def create_report(payload: AnalysisInput, user: CurrentUser = Depends(current_user)):
    ratelimit.hit("ai", user.id)
    ratelimit.consume_ai_quota(user.id, "report")
    now = utcnow()
    report_id = new_id()
    with db.transaction() as conn:
        conn.execute(insert(db.reports).values(
            id=report_id, user_id=user.id, title=payload.display_name()[:120], status="queued", stage="understand",
            progress=pipeline.PROGRESS["understand"], input=payload.model_dump(), state={}, result=None, error=None,
            engine_version=pipeline.ENGINE_VERSION, legacy=False, lock_until=None, created_at=now, updated_at=now))
    return {"id": report_id, "status": "queued", "stage": "understand"}


@router.post("/reports/{report_id}/advance")
def advance(report_id: str, user: CurrentUser = Depends(current_user)):
    with db.read() as conn:
        _own_report(conn, report_id, user.id)
    return pipeline.advance(report_id)


@router.get("/reports")
def list_reports(user: CurrentUser = Depends(current_user), limit: int = Query(50, le=100)):
    with db.read() as conn:
        rows = conn.execute(select(db.reports).where(db.reports.c.user_id == user.id)
                            .order_by(desc(db.reports.c.created_at)).limit(limit)).fetchall()
        validation = conn.execute(
            select(db.validation_items.c.report_id, db.validation_items.c.status, func.count())
            .where(db.validation_items.c.user_id == user.id)
            .group_by(db.validation_items.c.report_id, db.validation_items.c.status)).fetchall()
    progress: dict[str, dict[str, int]] = {}
    for report_id, status, count in validation:
        progress.setdefault(report_id, {})[status] = count
    return {"reports": [{**_summary(r), "validation": progress.get(r.id, {})} for r in rows]}


@router.get("/reports/{report_id}")
def get_report(report_id: str, user: CurrentUser = Depends(current_user)):
    with db.read() as conn:
        row = _own_report(conn, report_id, user.id)
    return {**_summary(row), "input": row.input, "result": row.result, "error": row.error,
            "status_detail": pipeline.status_payload(row)}


@router.delete("/reports/{report_id}")
def delete_report(report_id: str, user: CurrentUser = Depends(current_user)):
    with db.transaction() as conn:
        _own_report(conn, report_id, user.id)
        conn.execute(update(db.startups).where(db.startups.c.report_id == report_id).values(report_id=None))
        conn.execute(delete(db.reports).where(db.reports.c.id == report_id))
    return {"ok": True}


@router.get("/reports/{report_id}/export")
def export_report(report_id: str, format: str = Query("md", pattern="^(md|json)$"), user: CurrentUser = Depends(current_user)):
    with db.read() as conn:
        row = _own_report(conn, report_id, user.id)
    if not row.result:
        raise HTTPException(409, "The report is not finished yet.")
    filename = "".join(ch for ch in row.title if ch.isalnum() or ch in " -_")[:60].strip().replace(" ", "-") or "report"
    if format == "json":
        return Response(assistant.to_json({"title": row.title, "input": row.input, **row.result}), media_type="application/json",
                        headers={"Content-Disposition": f'attachment; filename="{filename}.json"'})
    return PlainTextResponse(assistant.export_markdown({"title": row.title, "result": row.result}), media_type="text/markdown",
                             headers={"Content-Disposition": f'attachment; filename="{filename}.md"'})


# ------------------------------------------------------------------------- legacy import
class LegacyReport(BaseModel):
    startup_name: str = Field(default="", max_length=120)
    industry: str = Field(default="", max_length=80)
    created_at: str = Field(default="", max_length=40)
    startup_score: int | None = None
    data: dict[str, Any] = Field(default_factory=dict)


class LegacyImport(BaseModel):
    reports: list[LegacyReport] = Field(max_length=20)


@router.post("/reports/import-legacy")
def import_legacy(payload: LegacyImport, user: CurrentUser = Depends(current_user)):
    """Preserve reports the previous version stored in the browser. They are clearly marked as legacy."""
    now = utcnow()
    imported = 0
    with db.transaction() as conn:
        for item in payload.reports:
            raw = {k: v for k, v in item.data.items() if isinstance(k, str)}
            text = str(raw.get("executive_summary") or "")[:4000]
            conn.execute(insert(db.reports).values(
                id=new_id(), user_id=user.id, title=clean_text(item.startup_name or "Imported report", 120),
                status="complete", stage="complete", progress=100,
                input={"idea": text or item.startup_name, "name": item.startup_name, "industry_legacy": item.industry},
                state={}, result={"legacy": True, "legacy_score": item.startup_score, "legacy_payload": raw,
                                  "title": item.startup_name, "imported_from": "browser localStorage (previous PunchStart version)"},
                error=None, engine_version="legacy-1.x", legacy=True, lock_until=None, created_at=now, updated_at=now,
                completed_at=now))
            imported += 1
    return {"imported": imported}


# -------------------------------------------------------------------------- assistant
class ChatIn(BaseModel):
    message: str = Field(min_length=1, max_length=2000)


@router.get("/reports/{report_id}/chat")
def chat_history(report_id: str, user: CurrentUser = Depends(current_user)):
    with db.read() as conn:
        _own_report(conn, report_id, user.id)
        rows = conn.execute(select(db.report_messages).where(db.report_messages.c.report_id == report_id)
                            .order_by(db.report_messages.c.created_at)).fetchall()
    return {"messages": [{"id": r.id, "role": r.role, "content": r.content, "meta": r.meta, "created_at": iso(r.created_at)}
                         for r in rows]}


@router.post("/reports/{report_id}/chat")
def chat(report_id: str, payload: ChatIn, user: CurrentUser = Depends(current_user)):
    ratelimit.hit("ai", user.id)
    with db.read() as conn:
        row = _own_report(conn, report_id, user.id)
        history = [{"role": r.role, "content": r.content} for r in conn.execute(
            select(db.report_messages.c.role, db.report_messages.c.content)
            .where(db.report_messages.c.report_id == report_id).order_by(db.report_messages.c.created_at))]
    if row.legacy or not row.result or row.result.get("legacy"):
        raise HTTPException(409, "The assistant needs a completed report from the current engine.")
    if not llm.available():
        raise HTTPException(503, "The AI engine is not configured on this server.")
    ratelimit.consume_ai_quota(user.id, "assistant")
    question = clean_text(payload.message, 2000)
    try:
        reply = assistant.answer({"title": row.title, **row.result}, history, question)
    except llm.LLMUnavailable:
        raise HTTPException(503, "The AI engine is temporarily unavailable (quota or timeout). Please try again later.")
    now = utcnow()
    with db.transaction() as conn:
        conn.execute(insert(db.report_messages).values(id=new_id(), report_id=report_id, user_id=user.id, role="user",
                                                       content=question, meta={}, created_at=now))
        message_id = new_id()
        meta = {k: reply[k] for k in ("answer_type", "sources", "follow_ups", "model", "citations_removed")}
        conn.execute(insert(db.report_messages).values(id=message_id, report_id=report_id, user_id=user.id, role="assistant",
                                                       content=reply["answer"], meta=meta, created_at=utcnow()))
    return {"id": message_id, "role": "assistant", "content": reply["answer"], "meta": meta}


# --------------------------------------------------------------------- validation tracker
class ValidationIn(BaseModel):
    title: str = Field(min_length=1, max_length=200)
    hypothesis: str = Field(default="", max_length=2000)
    method: str = Field(default="", max_length=2000)
    success_metric: str = Field(default="", max_length=1000)
    status: str = Field(default="todo", pattern="^(todo|running|validated|invalidated)$")
    notes: str = Field(default="", max_length=4000)


class ValidationPatch(BaseModel):
    title: str | None = Field(default=None, max_length=200)
    status: str | None = Field(default=None, pattern="^(todo|running|validated|invalidated)$")
    notes: str | None = Field(default=None, max_length=4000)
    success_metric: str | None = Field(default=None, max_length=1000)


def _item(r) -> dict:
    return {"id": r.id, "report_id": r.report_id, "title": r.title, "hypothesis": r.hypothesis, "method": r.method,
            "success_metric": r.success_metric, "status": r.status, "notes": r.notes, "updated_at": iso(r.updated_at)}


@router.get("/reports/{report_id}/validation")
def list_validation(report_id: str, user: CurrentUser = Depends(current_user)):
    with db.read() as conn:
        _own_report(conn, report_id, user.id)
        rows = conn.execute(select(db.validation_items).where(db.validation_items.c.report_id == report_id)
                            .order_by(db.validation_items.c.created_at)).fetchall()
    return {"items": [_item(r) for r in rows]}


@router.post("/reports/{report_id}/validation", status_code=201)
def add_validation(report_id: str, payload: ValidationIn, user: CurrentUser = Depends(current_user)):
    now = utcnow()
    with db.transaction() as conn:
        _own_report(conn, report_id, user.id)
        item_id = new_id()
        conn.execute(insert(db.validation_items).values(id=item_id, report_id=report_id, user_id=user.id,
                                                        **payload.model_dump(), created_at=now, updated_at=now))
        row = conn.execute(select(db.validation_items).where(db.validation_items.c.id == item_id)).first()
    return _item(row)


@router.patch("/validation/{item_id}")
def patch_validation(item_id: str, payload: ValidationPatch, user: CurrentUser = Depends(current_user)):
    values = {k: v for k, v in payload.model_dump().items() if v is not None}
    with db.transaction() as conn:
        row = conn.execute(select(db.validation_items).where(db.validation_items.c.id == item_id)).first()
        if row is None or row.user_id != user.id:
            raise HTTPException(404, "Item not found.")
        if values:
            conn.execute(update(db.validation_items).where(db.validation_items.c.id == item_id).values(**values, updated_at=utcnow()))
        row = conn.execute(select(db.validation_items).where(db.validation_items.c.id == item_id)).first()
    return _item(row)


@router.delete("/validation/{item_id}")
def delete_validation(item_id: str, user: CurrentUser = Depends(current_user)):
    with db.transaction() as conn:
        result = conn.execute(delete(db.validation_items).where(db.validation_items.c.id == item_id,
                                                                db.validation_items.c.user_id == user.id))
    if result.rowcount == 0:
        raise HTTPException(404, "Item not found.")
    return {"ok": True}


# ------------------------------------------------------------------------- watchlist
class WatchIn(BaseModel):
    company_id: str = Field(min_length=3, max_length=64)
    report_id: str | None = Field(default=None, max_length=24)
    note: str = Field(default="", max_length=1000)


@router.get("/watchlist")
def get_watchlist(user: CurrentUser = Depends(current_user)):
    with db.read() as conn:
        rows = conn.execute(select(db.watchlist).where(db.watchlist.c.user_id == user.id)
                            .order_by(desc(db.watchlist.c.created_at))).fetchall()
    items = []
    for r in rows:
        card = company_card(r.company_id)
        items.append({"id": r.id, "company_id": r.company_id, "name": r.name, "note": r.note, "report_id": r.report_id,
                      "created_at": iso(r.created_at), "company": card, "in_knowledge_base": card is not None})
    return {"items": items}


@router.post("/watchlist", status_code=201)
def add_watch(payload: WatchIn, user: CurrentUser = Depends(current_user)):
    card = company_card(payload.company_id)
    if card is None:
        raise HTTPException(404, "Company not found in the knowledge base.")
    with db.transaction() as conn:
        exists = conn.execute(select(db.watchlist.c.id).where(db.watchlist.c.user_id == user.id,
                                                              db.watchlist.c.company_id == payload.company_id)).first()
        if exists:
            return {"id": exists.id, "already": True}
        item_id = new_id()
        conn.execute(insert(db.watchlist).values(id=item_id, user_id=user.id, company_id=payload.company_id, name=card["name"],
                                                 report_id=payload.report_id, note=payload.note, created_at=utcnow()))
    return {"id": item_id}


@router.delete("/watchlist/{item_id}")
def remove_watch(item_id: str, user: CurrentUser = Depends(current_user)):
    with db.transaction() as conn:
        conn.execute(delete(db.watchlist).where(db.watchlist.c.id == item_id, db.watchlist.c.user_id == user.id))
    return {"ok": True}


# ---------------------------------------------------------------------------- compare
@router.get("/reports-compare")
def compare(ids: str = Query(..., max_length=200), user: CurrentUser = Depends(current_user)):
    wanted = [i for i in ids.split(",") if i][:4]
    if len(wanted) < 2:
        raise HTTPException(422, "Choose at least two reports to compare.")
    out = []
    with db.read() as conn:
        for report_id in wanted:
            row = _own_report(conn, report_id, user.id)
            result = row.result or {}
            if row.legacy or not result.get("scores"):
                raise HTTPException(409, f"'{row.title}' has no current-engine scores to compare.")
            comps = result.get("evidence", {}).get("competitors", {})
            out.append({
                "id": row.id, "title": row.title, "created_at": iso(row.created_at),
                "overall": result["scores"]["overall"], "confidence": result["scores"]["confidence"],
                "dimensions": {d["key"]: {"label": d["label"], "score": d["score"]} for d in result["scores"]["dimensions"]},
                "sector": ((result.get("classification", {}).get("sector") or {}).get("top") or [{}])[0].get("label"),
                "direct_competitors": [c["name"] for c in comps.get("direct", [])][:5],
                "verdict": next((m["value"] for m in (result.get("sections", {}).get("final_recommendations") or {}).get("metrics", [])
                                 if m.get("label", "").lower() == "verdict"), None),
                "market_sizing": (result.get("sections", {}).get("market_sizing") or {}).get("metrics", []),
            })
    return {"reports": out}
