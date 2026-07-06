import logging
from pathlib import Path

from fastapi import APIRouter, Depends, File, Form, HTTPException, Request, UploadFile
from fastapi.responses import HTMLResponse
from fastapi.templating import Jinja2Templates
from sqlalchemy.orm import Session

from app.config import Settings, get_settings
from app.db import get_db
from app.services.file_parser import extract_text_from_file
from app.services.ingest import ingest_minutes
from app.services.llm import LLMService

logger = logging.getLogger(__name__)

TEMPLATES_DIR = Path(__file__).resolve().parent.parent / "templates"
templates = Jinja2Templates(directory=str(TEMPLATES_DIR))

router = APIRouter(tags=["ui"])


def get_llm(settings: Settings = Depends(get_settings)) -> LLMService:
    return LLMService(settings)


@router.get("/", response_class=HTMLResponse)
def dashboard(request: Request, settings: Settings = Depends(get_settings)):
    return templates.TemplateResponse(
        "dashboard.html",
        {"request": request, "app_name": settings.app_name},
    )


@router.get("/app", response_class=HTMLResponse)
def upload_page(request: Request, settings: Settings = Depends(get_settings)):
    return templates.TemplateResponse(
        "upload.html",
        {"request": request, "app_name": settings.app_name},
    )


@router.post("/upload", response_class=HTMLResponse)
async def upload_minutes(
    request: Request,
    project_name: str = Form(...),
    meeting_title: str = Form(...),
    file: UploadFile = File(...),
    db: Session = Depends(get_db),
    llm: LLMService = Depends(get_llm),
    settings: Settings = Depends(get_settings),
):
    try:
        doc_text = extract_text_from_file(file, settings)
        if not doc_text or len(doc_text.strip()) < 10:
            return templates.TemplateResponse(
                "upload.html",
                {
                    "request": request,
                    "app_name": settings.app_name,
                    "error": f"Could not read text from {file.filename}. Upload a PDF, DOCX, or TXT with readable content.",
                },
                status_code=400,
            )

        result = ingest_minutes(
            db,
            llm,
            project_name=project_name.strip(),
            meeting_title=meeting_title.strip(),
            raw_text=doc_text,
            source_url=file.filename,
        )

        return templates.TemplateResponse(
            "result.html",
            {
                "request": request,
                "app_name": settings.app_name,
                "project_name": result["project_name"],
                "meeting_title": result["meeting_title"],
                "data": result["extracted"],
                "minutes_id": result["minutes_id"],
                "project_id": result["project_id"],
                "meeting_id": result["meeting_id"],
            },
        )
    except HTTPException:
        raise
    except Exception as exc:
        db.rollback()
        logger.exception("Upload failed")
        raise HTTPException(status_code=500, detail=f"Upload failed: {exc}") from exc


@router.get("/summary-ui", response_class=HTMLResponse)
def summary_ui(request: Request, settings: Settings = Depends(get_settings)):
    return templates.TemplateResponse(
        "summary.html",
        {"request": request, "app_name": settings.app_name},
    )


@router.get("/search-ui", response_class=HTMLResponse)
def search_ui(request: Request, settings: Settings = Depends(get_settings)):
    return templates.TemplateResponse(
        "search.html",
        {"request": request, "app_name": settings.app_name},
    )


@router.get("/items-ui", response_class=HTMLResponse)
def items_ui(request: Request, settings: Settings = Depends(get_settings)):
    return templates.TemplateResponse(
        "items.html",
        {"request": request, "app_name": settings.app_name},
    )


@router.get("/health-ui", response_class=HTMLResponse)
def health_ui(
    request: Request,
    db: Session = Depends(get_db),
    settings: Settings = Depends(get_settings),
    llm: LLMService = Depends(get_llm),
):
    from app.services.health import check_health

    health = check_health(db, settings, llm)
    return templates.TemplateResponse(
        "health.html",
        {
            "request": request,
            "app_name": settings.app_name,
            "health": health,
        },
    )
