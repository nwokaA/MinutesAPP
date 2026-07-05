import logging

from fastapi import APIRouter, Depends
from sqlalchemy import text
from sqlalchemy.orm import Session

from app.config import Settings, get_settings
from app.db import get_db
from app.schemas import HealthResponse
from app.services.llm import LLMService

logger = logging.getLogger(__name__)
router = APIRouter(tags=["health"])


def get_llm(settings: Settings = Depends(get_settings)) -> LLMService:
    return LLMService(settings)


@router.get("/health", response_model=HealthResponse)
def health(
    db: Session = Depends(get_db),
    settings: Settings = Depends(get_settings),
    llm: LLMService = Depends(get_llm),
):
    db_status = "ok"
    try:
        db.execute(text("SELECT 1"))
    except Exception as exc:
        logger.exception("Database health check failed")
        db_status = f"error: {exc}"

    ollama_status = "ok" if llm.ping() else "unavailable"

    overall = "healthy" if db_status == "ok" else "degraded"
    if db_status != "ok":
        overall = "unhealthy"

    return HealthResponse(
        status=overall,
        version=settings.app_version,
        db=db_status,
        ollama=ollama_status,
    )


@router.get("/health/db")
def health_db(db: Session = Depends(get_db)):
    db.execute(text("SELECT 1"))
    return {"db": "ok"}
