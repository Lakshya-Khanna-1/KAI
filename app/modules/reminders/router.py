from typing import List, Optional
from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session

from app.db.session import get_db
from app.modules.reminders import service
from app.modules.reminders.models import AlarmCreate, ReminderCreate, ReminderResponse, SnoozeRequest

router = APIRouter(prefix="/reminders", tags=["reminders"])


@router.post("", response_model=ReminderResponse, status_code=status.HTTP_201_CREATED)
def create_reminder_endpoint(payload: ReminderCreate, db: Session = Depends(get_db)):
    rem = service.set_reminder(
        db=db,
        text=payload.text,
        fire_at_str=payload.fire_at_str,
        recurrence_rule=payload.recurrence_rule,
        priority=payload.priority or "normal",
        source_task_id=payload.source_task_id,
    )
    return rem


@router.post("/alarm", response_model=ReminderResponse, status_code=status.HTTP_201_CREATED)
def create_alarm_endpoint(payload: AlarmCreate, db: Session = Depends(get_db)):
    alarm = service.set_alarm(
        db=db,
        text=payload.text,
        fire_at_str=payload.fire_at_str,
        recurrence_rule=payload.recurrence_rule,
    )
    return alarm


@router.get("", response_model=List[ReminderResponse])
def list_reminders_endpoint(
    status: str = "pending",
    priority: Optional[str] = None,
    limit: int = 50,
    db: Session = Depends(get_db)
):
    return service.list_reminders(db=db, status=status, priority=priority, limit=limit)


@router.post("/{reminder_id}/snooze", response_model=ReminderResponse)
def snooze_reminder_endpoint(reminder_id: str, payload: SnoozeRequest, db: Session = Depends(get_db)):
    rem = service.snooze_reminder(db=db, reminder_id_or_text=reminder_id, snooze_duration_str=payload.snooze_duration_str)
    if not rem:
        raise HTTPException(status_code=404, detail="Reminder not found")
    return rem


@router.post("/{reminder_id}/ack", response_model=ReminderResponse)
def ack_alarm_endpoint(reminder_id: str, db: Session = Depends(get_db)):
    rem = service.ack_alarm(db=db, reminder_id_or_text=reminder_id)
    if not rem:
        raise HTTPException(status_code=404, detail="Reminder not found")
    return rem


@router.delete("/{reminder_id}")
def cancel_reminder_endpoint(reminder_id: str, db: Session = Depends(get_db)):
    ok = service.cancel_reminder(db=db, reminder_id_or_text=reminder_id)
    if not ok:
        raise HTTPException(status_code=404, detail="Reminder not found")
    return {"message": "Reminder cancelled successfully"}
