from datetime import datetime
from typing import Optional
from pydantic import BaseModel, ConfigDict, Field


class ReminderCreate(BaseModel):
    text: str = Field(..., description="Reminder or alarm text")
    fire_at_str: str = Field(..., description="Natural language fire time, e.g. 'in 15 mins', 'tomorrow 8am'")
    recurrence_rule: Optional[str] = Field(None, description="Optional RRULE string or natural recurrence like 'every day'")
    priority: Optional[str] = Field("normal", description="Priority: 'normal', 'high', 'alarm'")
    source_task_id: Optional[str] = Field(None, description="Optional source task ID")


class AlarmCreate(BaseModel):
    text: str = Field(..., description="Alarm text/title")
    fire_at_str: str = Field(..., description="Natural language fire time, e.g. 'tomorrow 7am', 'every weekday 6am'")
    recurrence_rule: Optional[str] = Field(None, description="Optional recurrence rule")


class SnoozeRequest(BaseModel):
    snooze_duration_str: str = Field("10 mins", description="Duration to snooze, e.g. '10 mins', '1 hour'")


class ReminderResponse(BaseModel):
    id: str
    text: str
    fire_at: datetime
    recurrence_rule: Optional[str] = None
    status: str
    priority: str
    snoozed_until: Optional[datetime] = None
    source_task_id: Optional[str] = None
    created_at: datetime
    fired_at: Optional[datetime] = None

    model_config = ConfigDict(from_attributes=True)
