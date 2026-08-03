import logging
from typing import Any, Dict, Optional
from sqlalchemy.orm import Session

from app.modules.reminders import service as reminder_service
from app.modules.tasks import service as task_service

logger = logging.getLogger(__name__)


def handle_notification_action_done(db: Session, entity_type: str, entity_id: str) -> Dict[str, Any]:
    """
    Callback handler for 'Done' button on notification.
    If entity_type == 'task': completes task.
    If entity_type == 'reminder' or default: completes/acks reminder.
    """
    if entity_type == "task":
        task = task_service.complete_task(db=db, task_id_or_title=entity_id)[0]
        if task:
            return {"status": "success", "message": f"Task '{task.title}' completed", "entity": "task"}
        return {"status": "error", "message": "Task not found"}
    else:
        # Default to reminder
        rem = reminder_service.ack_alarm(db=db, reminder_id_or_text=entity_id)
        if rem:
            return {"status": "success", "message": f"Reminder '{rem.text}' completed/acked", "entity": "reminder"}
        return {"status": "error", "message": "Reminder not found"}


def handle_notification_action_snooze(db: Session, entity_type: str, entity_id: str, duration: str = "10m") -> Dict[str, Any]:
    """
    Callback handler for 'Snooze 10m' button on notification.
    """
    rem = reminder_service.snooze_reminder(db=db, reminder_id_or_text=entity_id, snooze_duration_str=duration)
    if rem:
        return {"status": "success", "message": f"Reminder '{rem.text}' snoozed for {duration}", "entity": "reminder"}
    return {"status": "error", "message": "Reminder not found"}
