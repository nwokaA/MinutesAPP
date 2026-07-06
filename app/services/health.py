from dataclasses import dataclass

from sqlalchemy import text
from sqlalchemy.orm import Session

from app.config import Settings
from app.services.llm import LLMService


@dataclass
class HealthStatus:
    status: str
    version: str
    db: str
    ollama: str
    db_ok: bool
    ollama_ok: bool


def check_health(db: Session, settings: Settings, llm: LLMService) -> HealthStatus:
    db_status = "ok"
    db_ok = True
    try:
        db.execute(text("SELECT 1"))
    except Exception as exc:
        db_status = str(exc)
        db_ok = False

    ollama_ok = llm.ping()
    ollama_status = "ok" if ollama_ok else "unavailable"

    if db_ok and ollama_ok:
        overall = "healthy"
    elif db_ok:
        overall = "degraded"
    else:
        overall = "unhealthy"

    return HealthStatus(
        status=overall,
        version=settings.app_version,
        db=db_status,
        ollama=ollama_status,
        db_ok=db_ok,
        ollama_ok=ollama_ok,
    )
