from typing import Any, Dict, Optional
from pydantic import BaseModel, Field
from datetime import datetime

class ProfileItem(BaseModel):
    key: str
    value: Any
    updated_at: Optional[datetime] = None
    asked_at: Optional[datetime] = None

class OnboardingStatus(BaseModel):
    phase: str = Field("in_progress", description="in_progress, completed, or skipped")
    questions_asked: int = 0
    session_questions_asked: int = 0
    completed_at: Optional[datetime] = None
    profile: Dict[str, Any] = {}

class UpdateProfilePayload(BaseModel):
    key: str = Field(..., description="Profile key e.g. name, timezone, wake_time, sleep_time, work_hours, ai_ml_skill, target_role, study_hours, gym_split, diet, communication_style, motivation, annoyances")
    value: Any = Field(..., description="Value to store in user profile")

class OnboardingTriggerPayload(BaseModel):
    action: str = Field("resume", description="start, resume, skip, reset")
