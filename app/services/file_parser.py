from io import BytesIO

import docx2txt
import pdfplumber
from fastapi import HTTPException, UploadFile

from app.config import Settings


def extract_text_from_file(upload: UploadFile, settings: Settings) -> str:
    """Read PDF/DOCX/TXT into a single text string."""
    name = (upload.filename or "").lower()
    content = upload.file.read()
    upload.file.seek(0)

    if len(content) > settings.max_upload_bytes:
        raise HTTPException(
            status_code=413,
            detail=f"File exceeds maximum size of {settings.max_upload_bytes // (1024 * 1024)} MB",
        )

    if not any(name.endswith(ext) for ext in settings.allowed_extensions):
        allowed = ", ".join(settings.allowed_extensions)
        raise HTTPException(status_code=400, detail=f"Unsupported file type. Allowed: {allowed}")

    if name.endswith(".pdf") or upload.content_type == "application/pdf":
        txt_parts = []
        with pdfplumber.open(BytesIO(content)) as pdf:
            for page in pdf.pages:
                page_text = page.extract_text() or ""
                if page_text.strip():
                    txt_parts.append(page_text)
        return "\n\n".join(txt_parts).strip()

    if name.endswith(".docx") or upload.content_type in (
        "application/vnd.openxmlformats-officedocument.wordprocessingml.document",
    ):
        return (docx2txt.process(BytesIO(content)) or "").strip()

    if upload.content_type in ("text/plain", "text/markdown") or name.endswith((".txt", ".md")):
        return content.decode("utf-8", errors="ignore")

    return content.decode("utf-8", errors="ignore")
