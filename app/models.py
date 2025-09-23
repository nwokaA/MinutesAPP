from sqlalchemy import (
    Column, Integer, String, Text, Date, DateTime, Enum, ForeignKey
)
from .db import Base

item_type = Enum("decision", "action", "accomplishment", "risk", "issue", "blocker", name="item_type")
item_status = Enum("open", "in_progress", "done", name="item_status")

class Project(Base):
    __tablename__ = "projects"
    id = Column(Integer, primary_key=True)
    name = Column(String, unique=True, nullable=False)
    sponsor = Column(String, nullable=True)
    start_date = Column(Date, nullable=True)
    target_end = Column(Date, nullable=True)
    status = Column(String, nullable=True)

class Meeting(Base):
    __tablename__ = "meetings"
    id = Column(Integer, primary_key=True)
    project_id = Column(Integer, ForeignKey("projects.id"))
    title = Column(String, nullable=True)
    start_ts = Column(DateTime(timezone=True), nullable=True)
    end_ts = Column(DateTime(timezone=True), nullable=True)
    cadence = Column(String, nullable=True)

class Minutes(Base):
    __tablename__ = "minutes"
    id = Column(Integer, primary_key=True)
    meeting_id = Column(Integer, ForeignKey("meetings.id"))
    ts = Column(DateTime(timezone=True), nullable=True)
    source_url = Column(String, nullable=True)
    raw_text = Column(Text, nullable=False)
    # embedding is stored via raw SQL, not modeled here

class Item(Base):
    __tablename__ = "items"
    id = Column(Integer, primary_key=True)
    minutes_id = Column(Integer, ForeignKey("minutes.id"))
    project_id = Column(Integer, ForeignKey("projects.id"))
    type = Column(item_type, nullable=False)

    title = Column(String, nullable=True)
    detail = Column(Text, nullable=True)
    owner = Column(String, nullable=True)
    due_date = Column(Date, nullable=True)
    status = Column(item_status, nullable=False, default="open")
    priority = Column(Integer, nullable=True)
    severity = Column(Integer, nullable=True)
    evidence_start = Column(Integer, nullable=True)
    evidence_end = Column(Integer, nullable=True)
    confidence = Column(Integer, nullable=True)  # change to Float later if you like
