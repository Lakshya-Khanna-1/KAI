import uuid
from datetime import datetime, timezone
from sqlalchemy import Column, String, Integer, Boolean, DateTime, Text, ForeignKey
from app.db.base import Base

def now_utc():
    return datetime.now(timezone.utc)

def generate_uuid():
    return str(uuid.uuid4())

class ScheduleBlock(Base):
    __tablename__ = "schedule_blocks"

    id = Column(String, primary_key=True, default=generate_uuid)
    date = Column(String, nullable=False, index=True)  # YYYY-MM-DD
    start_at = Column(DateTime(timezone=True), nullable=False)
    end_at = Column(DateTime(timezone=True), nullable=False)
    type = Column(String, nullable=False, default="routine")  # commitment, gym, study, buffer, free, routine
    title = Column(String, nullable=False)
    linked_id = Column(String, nullable=True)  # Link to task_id, roadmap_topic_id, workout_id
    locked = Column(Boolean, default=False)
    status = Column(String, default="scheduled")  # scheduled, in_progress, completed, missed, rescheduled
    actual_start = Column(DateTime(timezone=True), nullable=True)
    actual_end = Column(DateTime(timezone=True), nullable=True)

class AvailabilityRule(Base):
    __tablename__ = "availability_rules"

    id = Column(String, primary_key=True, default=generate_uuid)
    weekday = Column(Integer, nullable=False)  # 0=Monday, 6=Sunday
    start_time = Column(String, nullable=False)  # "09:00"
    end_time = Column(String, nullable=False)    # "17:00"
    kind = Column(String, nullable=False, default="work")  # work, study, gym, free, sleep
