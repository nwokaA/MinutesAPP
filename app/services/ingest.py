import re
from typing import Any, Optional

from sqlalchemy import text
from sqlalchemy.orm import Session

from app.models import Item, Meeting, Minutes, Project
from app.services.llm import LLMService


def clean_date(val: Optional[str]) -> Optional[str]:
    if not val:
        return None
    val = str(val).strip()
    if val == "":
        return None
    if re.fullmatch(r"\d{4}-\d{2}-\d{2}", val):
        return val
    return None


def norm_text(value: Any) -> Optional[str]:
    if value is None:
        return None
    if isinstance(value, (int, float)):
        return str(value)
    if isinstance(value, (list, tuple)):
        return ", ".join(str(v) for v in value if str(v).strip())
    if isinstance(value, dict):
        if len(value) <= 3:
            parts = []
            for key, val in value.items():
                if isinstance(val, bool) and val is True:
                    parts.append(str(key))
                else:
                    parts.append(f"{key}: {val}")
            return ", ".join(parts) if parts else None
        import json

        return json.dumps(value, ensure_ascii=False)
    text_val = str(value).strip()
    return text_val or None


def norm_int(value: Any) -> Optional[int]:
    if value in (None, "", [], {}):
        return None
    try:
        num = int(value)
        return num if num != 0 else None
    except (TypeError, ValueError):
        return None


def norm_float(value: Any) -> Optional[float]:
    if value in (None, "", [], {}):
        return None
    try:
        return float(value)
    except (TypeError, ValueError):
        return None


def ingest_minutes(
    db: Session,
    llm: LLMService,
    *,
    project_name: str,
    meeting_title: str,
    raw_text: str,
    source_url: Optional[str] = None,
) -> dict[str, Any]:
    proj = db.query(Project).filter_by(name=project_name).first()
    if not proj:
        proj = Project(name=project_name)
        db.add(proj)
        db.flush()

    mtg = Meeting(project_id=proj.id, title=meeting_title)
    db.add(mtg)
    db.flush()

    mins = Minutes(meeting_id=mtg.id, source_url=source_url, raw_text=raw_text)
    db.add(mins)
    db.flush()

    vec = llm.embed(raw_text)
    db.execute(
        text("UPDATE minutes SET embedding = (:v)::vector WHERE id = :id"),
        {"v": vec, "id": mins.id},
    )

    data = llm.extract(raw_text)

    def insert_items(items: list[dict[str, Any]] | None, item_type: str) -> None:
        for item in items or []:
            evidence = item.get("evidence_span") or {}
            db.add(
                Item(
                    minutes_id=mins.id,
                    project_id=proj.id,
                    type=item_type,
                    title=norm_text(item.get("title")),
                    detail=norm_text(item.get("detail")),
                    owner=norm_text(item.get("owner")),
                    due_date=clean_date(item.get("due_date") or item.get("date")),
                    priority=norm_int(item.get("priority")),
                    severity=norm_int(item.get("severity")),
                    evidence_start=evidence.get("start"),
                    evidence_end=evidence.get("end"),
                    confidence=norm_float(item.get("confidence")),
                )
            )

    insert_items(data.get("decisions"), "decision")
    insert_items(data.get("actions"), "action")
    insert_items(data.get("accomplishments"), "accomplishment")
    insert_items(data.get("risks"), "risk")
    insert_items(data.get("issues"), "issue")

    db.commit()

    return {
        "project_id": proj.id,
        "meeting_id": mtg.id,
        "minutes_id": mins.id,
        "project_name": project_name,
        "meeting_title": meeting_title,
        "extracted": data,
    }
