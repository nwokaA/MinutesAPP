import logging

from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session

from app.config import Settings, get_settings
from app.db import get_db
from app.schemas import HealthResponse
from app.services.health import check_health
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
    result = check_health(db, settings, llm)
    return HealthResponse(
        status=result.status,
        version=result.version,
        db=result.db,
        ollama=result.ollama,
    )


@router.get("/health/db")
def health_db(db: Session = Depends(get_db)):
    from sqlalchemy import text

    db.execute(text("SELECT 1"))
    return {"db": "ok"}
