from datetime import datetime
from typing import Optional
from pydantic import BaseModel, ConfigDict, Field


class TaskCreate(BaseModel):
    title: str = Field(..., description="Title of the task")
    notes: Optional[str] = Field(None, description="Optional notes or details")
    due_date_str: Optional[str] = Field(None, description="Natural language due date, e.g. 'tomorrow 7am' or 'in 20 mins'")
    priority: Optional[str] = Field(None, description="Priority: low, medium, high, urgent. Inferred if omitted.")
    project: Optional[str] = Field(None, description="Optional project or folder grouping")
    recurrence_rule: Optional[str] = Field(None, description="Optional RRULE string or natural recurrence like 'every weekday 6pm'")


class TaskUpdate(BaseModel):
    title: Optional[str] = None
    notes: Optional[str] = None
    due_date_str: Optional[str] = None
    priority: Optional[str] = None
    project: Optional[str] = None
    status: Optional[str] = None
    recurrence_rule: Optional[str] = None


class TaskResponse(BaseModel):
    id: str
    title: str
    notes: Optional[str] = None
    priority: str
    due_at: Optional[datetime] = None
    project: Optional[str] = None
    status: str
    created_at: datetime
    completed_at: Optional[datetime] = None
    recurrence_rule: Optional[str] = None

    model_config = ConfigDict(from_attributes=True)
