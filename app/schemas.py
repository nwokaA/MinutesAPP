from typing import Any, Literal, Optional

from pydantic import BaseModel, Field


class IngestPayload(BaseModel):
    project_name: str = Field(..., min_length=1, max_length=500)
    meeting_title: str = Field(..., min_length=1, max_length=500)
    raw_text: str = Field(..., min_length=10)
    source_url: Optional[str] = Field(None, max_length=2000)


class HealthResponse(BaseModel):
    status: str
    version: str
    db: str
    ollama: str


class ProjectOut(BaseModel):
    id: int
    name: str


class SearchResult(BaseModel):
    minutes_id: int
    project_id: int
    similarity: float
    project_name: Optional[str] = None
    meeting_title: Optional[str] = None
    excerpt: Optional[str] = None
    source_url: Optional[str] = None


class ItemUpdate(BaseModel):
    status: Optional[Literal["open", "in_progress", "done"]] = None
    owner: Optional[str] = Field(None, max_length=500)
    due_date: Optional[str] = Field(None, description="YYYY-MM-DD or empty to clear")
    title: Optional[str] = Field(None, max_length=500)


class ItemOut(BaseModel):
    id: int
    minutes_id: int
    project_id: int
    type: str
    title: Optional[str] = None
    detail: Optional[str] = None
    owner: Optional[str] = None
    due_date: Optional[str] = None
    status: Optional[str] = None
    priority: Optional[int] = None
    severity: Optional[int] = None
    confidence: Optional[float] = None


class SummaryStats(BaseModel):
    counts: dict[str, int]


class SummaryActions(BaseModel):
    overdue: list[dict[str, Any]]
    due_soon: list[dict[str, Any]]
    open_other: list[dict[str, Any]]


class SummaryResponse(BaseModel):
    project_id: int
    window_days: int
    decisions: list[dict[str, Any]]
    accomplishments: list[dict[str, Any]]
    risks: list[dict[str, Any]]
    issues: list[dict[str, Any]]
    actions: SummaryActions
    stats: SummaryStats
    plan: Optional[str] = None
