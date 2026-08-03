from datetime import datetime, timezone
import uuid
from sqlalchemy import Column, String, Text, DateTime, Integer
from app.db.base import Base

def now_utc():
    return datetime.now(timezone.utc)

class Profile(Base):
    __tablename__ = "profile"

    key = Column(String, primary_key=True)
    value_json = Column(Text, nullable=True)
    updated_at = Column(DateTime, default=now_utc, onupdate=now_utc)
    asked_at = Column(DateTime, nullable=True)

class OnboardingState(Base):
    __tablename__ = "onboarding_state"

    id = Column(String, primary_key=True, default=lambda: str(uuid.uuid4()))
    phase = Column(String, default="in_progress")  # in_progress, completed, skipped
    questions_asked = Column(Integer, default=0)
    completed_at = Column(DateTime, nullable=True)
