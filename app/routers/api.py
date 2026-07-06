import logging
from datetime import date, datetime, timedelta
from typing import Any, Optional

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy import text
from sqlalchemy.orm import Session

from app.config import Settings, get_settings
from app.db import get_db
from app.schemas import IngestPayload, ItemOut, ItemUpdate, ProjectOut, SearchResult
from app.services.ingest import clean_date, ingest_minutes
from app.services.llm import LLMService

logger = logging.getLogger(__name__)
router = APIRouter(tags=["api"])

ITEM_TYPES = {"decision", "action", "accomplishment", "risk", "issue", "blocker"}
ITEM_STATUSES = {"open", "in_progress", "done"}


def serialize_item(row: Any) -> dict[str, Any]:
    item = dict(row)
    if isinstance(item.get("due_date"), date):
        item["due_date"] = item["due_date"].isoformat()
    return item


def get_llm(settings: Settings = Depends(get_settings)) -> LLMService:
    return LLMService(settings)


@router.post("/ingest")
def ingest(
    payload: IngestPayload,
    db: Session = Depends(get_db),
    llm: LLMService = Depends(get_llm),
):
    try:
        result = ingest_minutes(
            db,
            llm,
            project_name=payload.project_name,
            meeting_title=payload.meeting_title,
            raw_text=payload.raw_text,
            source_url=payload.source_url,
        )
        return {
            "ok": True,
            "project_id": result["project_id"],
            "meeting_id": result["meeting_id"],
            "minutes_id": result["minutes_id"],
        }
    except Exception as exc:
        db.rollback()
        logger.exception("Ingest failed")
        raise HTTPException(status_code=500, detail=str(exc)) from exc


@router.get("/search", response_model=list[SearchResult])
def search(
    q: str = Query(..., min_length=1),
    k: int = Query(5, ge=1, le=50),
    project_id: Optional[int] = None,
    detail: bool = Query(False, description="Include meeting title, excerpt, and project name"),
    db: Session = Depends(get_db),
    llm: LLMService = Depends(get_llm),
):
    try:
        qvec = llm.embed(q)
        where = "m.embedding IS NOT NULL"
        params: dict[str, Any] = {"qvec": qvec, "k": k}
        if project_id is not None:
            where += " AND mt.project_id = :pid"
            params["pid"] = project_id

        if detail:
            rows = db.execute(
                text(f"""
                    SELECT
                      m.id AS minutes_id,
                      mt.project_id AS project_id,
                      p.name AS project_name,
                      mt.title AS meeting_title,
                      LEFT(m.raw_text, 400) AS excerpt,
                      m.source_url,
                      1 - (m.embedding <=> (:qvec)::vector) AS score
                    FROM minutes m
                    JOIN meetings mt ON mt.id = m.meeting_id
                    JOIN projects p ON p.id = mt.project_id
                    WHERE {where}
                    ORDER BY m.embedding <=> (:qvec)::vector
                    LIMIT :k
                """),
                params,
            ).mappings().all()
            return [
                SearchResult(
                    minutes_id=r["minutes_id"],
                    project_id=r["project_id"],
                    similarity=float(r["score"]),
                    project_name=r["project_name"],
                    meeting_title=r["meeting_title"],
                    excerpt=r["excerpt"],
                    source_url=r["source_url"],
                )
                for r in rows
            ]

        rows = db.execute(
            text(f"""
                SELECT
                  m.id AS minutes_id,
                  mt.project_id AS project_id,
                  1 - (m.embedding <=> (:qvec)::vector) AS score
                FROM minutes m
                JOIN meetings mt ON mt.id = m.meeting_id
                WHERE {where}
                ORDER BY m.embedding <=> (:qvec)::vector
                LIMIT :k
            """),
            params,
        ).mappings().all()

        return [
            SearchResult(
                minutes_id=r["minutes_id"],
                project_id=r["project_id"],
                similarity=float(r["score"]),
            )
            for r in rows
        ]
    except Exception as exc:
        logger.exception("Search failed")
        raise HTTPException(status_code=500, detail=f"Search failed: {exc}") from exc


@router.get("/items")
def list_items(
    project_id: Optional[int] = Query(None),
    typ: Optional[str] = Query(None, description="decision|action|accomplishment|risk|issue|blocker"),
    status: Optional[str] = Query(None, description="open|in_progress|done"),
    due_before: Optional[str] = Query(None, description="YYYY-MM-DD"),
    due_after: Optional[str] = Query(None, description="YYYY-MM-DD"),
    limit: int = Query(50, ge=1, le=500),
    db: Session = Depends(get_db),
):
    try:
        where = []
        params: dict[str, Any] = {"lim": limit}
        if project_id is not None:
            where.append("i.project_id = :pid")
            params["pid"] = project_id
        if typ:
            where.append("i.type = :typ")
            params["typ"] = typ
        if status:
            where.append("i.status = :st")
            params["st"] = status
        if due_before:
            where.append("i.due_date IS NOT NULL AND i.due_date <= :db")
            params["db"] = due_before
        if due_after:
            where.append("i.due_date IS NOT NULL AND i.due_date >= :da")
            params["da"] = due_after
        wsql = ("WHERE " + " AND ".join(where)) if where else ""

        rows = db.execute(
            text(f"""
                SELECT i.id, i.minutes_id, i.project_id, i.type, i.title, i.detail, i.owner,
                       i.due_date, i.status, i.priority, i.severity, i.confidence
                FROM items i
                {wsql}
                ORDER BY i.id DESC
                LIMIT :lim
            """),
            params,
        ).mappings().all()

        out = [serialize_item(row) for row in rows]
        return out
    except Exception as exc:
        logger.exception("List items failed")
        raise HTTPException(status_code=500, detail=f"Items query failed: {exc}") from exc


@router.patch("/items/{item_id}", response_model=ItemOut)
def update_item(
    item_id: int,
    payload: ItemUpdate,
    db: Session = Depends(get_db),
):
    updates = payload.model_dump(exclude_unset=True)
    if not updates:
        raise HTTPException(status_code=400, detail="No fields to update")

    if "status" in updates and updates["status"] not in ITEM_STATUSES:
        raise HTTPException(status_code=400, detail="Invalid status")

    if "due_date" in updates:
        due = updates["due_date"]
        if due in ("", None):
            updates["due_date"] = None
        else:
            cleaned = clean_date(due)
            if not cleaned:
                raise HTTPException(status_code=400, detail="due_date must be YYYY-MM-DD")
            updates["due_date"] = cleaned

    if "owner" in updates and updates["owner"] is not None:
        updates["owner"] = updates["owner"].strip() or None

    if "title" in updates and updates["title"] is not None:
        updates["title"] = updates["title"].strip() or None

    set_clause = ", ".join(f"{key} = :{key}" for key in updates)
    params = {**updates, "id": item_id}

    try:
        result = db.execute(
            text(f"""
                UPDATE items
                SET {set_clause}
                WHERE id = :id
                RETURNING id, minutes_id, project_id, type, title, detail, owner,
                          due_date, status, priority, severity, confidence
            """),
            params,
        ).mappings().first()

        if not result:
            raise HTTPException(status_code=404, detail="Item not found")

        db.commit()
        return serialize_item(result)
    except HTTPException:
        db.rollback()
        raise
    except Exception as exc:
        db.rollback()
        logger.exception("Update item failed")
        raise HTTPException(status_code=500, detail=f"Update failed: {exc}") from exc


@router.get("/summary")
def summary(
    project_id: int = Query(...),
    days: int = Query(7, ge=1, le=60),
    plan: bool = Query(False),
    profile: str = Query("", description="Optional profile text to steer the plan"),
    db: Session = Depends(get_db),
    llm: LLMService = Depends(get_llm),
):
    try:
        since = datetime.utcnow() - timedelta(days=days)

        rows = db.execute(
            text("""
                SELECT i.id, i.type, i.title, i.detail, i.owner, i.due_date, i.priority, i.severity,
                       m.ts AS minutes_ts
                FROM items i
                JOIN minutes m ON m.id = i.minutes_id
                JOIN meetings mt ON mt.id = m.meeting_id
                WHERE mt.project_id = :pid
                  AND (m.ts IS NULL OR m.ts >= :since)
                ORDER BY i.id DESC
                LIMIT 1000
            """),
            {"pid": project_id, "since": since},
        ).mappings().all()

        decisions, accomplishments, risks, issues = [], [], [], []
        actions_overdue, actions_due_soon, actions_open = [], [], []
        today = date.today()
        soon_cutoff = today + timedelta(days=7)

        def as_dict(row: Any) -> dict[str, Any]:
            item = dict(row)
            if isinstance(item.get("due_date"), date):
                item["due_date"] = item["due_date"].isoformat()
            if isinstance(item.get("minutes_ts"), datetime):
                item["minutes_ts"] = item["minutes_ts"].isoformat()
            return item

        for row in rows:
            item_type = row["type"]
            if item_type == "decision":
                decisions.append(as_dict(row))
            elif item_type == "accomplishment":
                accomplishments.append(as_dict(row))
            elif item_type == "risk":
                risks.append(as_dict(row))
            elif item_type in ("issue", "blocker"):
                issues.append(as_dict(row))
            elif item_type == "action":
                due = row["due_date"]
                if isinstance(due, date):
                    if due < today:
                        actions_overdue.append(as_dict(row))
                    elif today <= due <= soon_cutoff:
                        actions_due_soon.append(as_dict(row))
                    else:
                        actions_open.append(as_dict(row))
                else:
                    actions_open.append(as_dict(row))

        out: dict[str, Any] = {
            "project_id": project_id,
            "window_days": days,
            "decisions": decisions,
            "accomplishments": accomplishments,
            "risks": risks,
            "issues": issues,
            "actions": {
                "overdue": actions_overdue,
                "due_soon": actions_due_soon,
                "open_other": actions_open,
            },
            "stats": {
                "counts": {
                    "decisions": len(decisions),
                    "accomplishments": len(accomplishments),
                    "risks": len(risks),
                    "issues": len(issues),
                    "actions_overdue": len(actions_overdue),
                    "actions_due_soon": len(actions_due_soon),
                    "actions_open_other": len(actions_open),
                }
            },
        }

        if plan:
            ctx_parts = []
            if decisions:
                ctx_parts.append("Decisions:\n" + "\n".join(f"- {d.get('title')}" for d in decisions[:10]))
            if accomplishments:
                ctx_parts.append(
                    "Accomplishments:\n" + "\n".join(f"- {a.get('title')}" for a in accomplishments[:10])
                )
            if actions_overdue or actions_due_soon:
                overdue_text = "\n".join(
                    f"- {a.get('title')} (owner: {a.get('owner')}, due: {a.get('due_date')})"
                    for a in actions_overdue[:10]
                )
                due_soon_text = "\n".join(
                    f"- {a.get('title')} (owner: {a.get('owner')}, due: {a.get('due_date')})"
                    for a in actions_due_soon[:10]
                )
                if overdue_text:
                    ctx_parts.append("Overdue Actions:\n" + overdue_text)
                if due_soon_text:
                    ctx_parts.append("Due Soon (<=7d):\n" + due_soon_text)
            if risks or issues:
                risk_text = "\n".join(
                    f"- {r.get('title')} (sev: {r.get('severity')})" for r in (risks + issues)[:10]
                )
                ctx_parts.append("Risks/Issues:\n" + risk_text)

            context = "\n\n".join(ctx_parts) if ctx_parts else "No significant items in the window."
            out["plan"] = llm.generate_plan(profile, context)

        return out
    except Exception as exc:
        logger.exception("Summary failed")
        raise HTTPException(status_code=500, detail=f"Summary failed: {exc}") from exc


@router.post("/reembed")
def reembed(
    project_id: Optional[int] = Query(None),
    db: Session = Depends(get_db),
    llm: LLMService = Depends(get_llm),
):
    try:
        where = "m.embedding IS NULL"
        params: dict[str, Any] = {}
        if project_id is not None:
            where += " AND mt.project_id = :pid"
            params["pid"] = project_id

        rows = db.execute(
            text(f"""
                SELECT m.id, m.raw_text
                FROM minutes m
                JOIN meetings mt ON mt.id = m.meeting_id
                WHERE {where}
                ORDER BY m.id
                LIMIT 5000
            """),
            params,
        ).mappings().all()

        updated = 0
        for row in rows:
            vec = llm.embed(row["raw_text"])
            db.execute(
                text("UPDATE minutes SET embedding = (:v)::vector WHERE id = :id"),
                {"v": vec, "id": row["id"]},
            )
            updated += 1

        db.commit()
        return {"updated": updated}
    except Exception as exc:
        db.rollback()
        logger.exception("Reembed failed")
        raise HTTPException(status_code=500, detail=f"Reembed failed: {exc}") from exc


@router.get("/projects", response_model=list[ProjectOut])
def list_projects(db: Session = Depends(get_db)):
    rows = db.execute(text("SELECT id, name FROM projects ORDER BY name")).mappings().all()
    return [ProjectOut(id=r["id"], name=r["name"]) for r in rows]
