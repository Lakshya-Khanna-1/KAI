import uuid
from datetime import datetime, timezone
from sqlalchemy import Column, String, Integer, Float, Boolean, DateTime, Text, ForeignKey
from sqlalchemy.orm import relationship
from app.db.base import Base

def now_utc():
    return datetime.now(timezone.utc)

def generate_uuid():
    return str(uuid.uuid4())

class Roadmap(Base):
    __tablename__ = "roadmaps"

    id = Column(String, primary_key=True, default=generate_uuid)
    name = Column(String, nullable=False)
    source_text = Column(Text, nullable=True)
    active = Column(Boolean, default=True)
    created_at = Column(DateTime(timezone=True), default=now_utc)
    updated_at = Column(DateTime(timezone=True), default=now_utc, onupdate=now_utc)

    phases = relationship("RoadmapPhase", back_populates="roadmap", cascade="all, delete-orphan", order_by="RoadmapPhase.order_index")

class RoadmapPhase(Base):
    __tablename__ = "roadmap_phases"

    id = Column(String, primary_key=True, default=generate_uuid)
    roadmap_id = Column(String, ForeignKey("roadmaps.id"), nullable=False)
    name = Column(String, nullable=False)
    order_index = Column(Integer, default=0)
    description = Column(Text, nullable=True)

    roadmap = relationship("Roadmap", back_populates="phases")
    topics = relationship("RoadmapTopic", back_populates="phase", cascade="all, delete-orphan", order_by="RoadmapTopic.order_index")

class RoadmapTopic(Base):
    __tablename__ = "roadmap_topics"

    id = Column(String, primary_key=True, default=generate_uuid)
    phase_id = Column(String, ForeignKey("roadmap_phases.id"), nullable=False)
    title = Column(String, nullable=False)
    est_hours = Column(Float, default=2.0)
    hours_done = Column(Float, default=0.0)
    status = Column(String, default="not_started")  # not_started, in_progress, completed
    prerequisites_json = Column(Text, default="[]")  # List of topic titles/IDs
    resources_json = Column(Text, default="[]")      # List of URLs/links
    order_index = Column(Integer, default=0)
    raw_line = Column(Text, nullable=True)

    phase = relationship("RoadmapPhase", back_populates="topics")
