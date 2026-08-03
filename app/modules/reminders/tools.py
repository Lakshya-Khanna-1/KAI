from typing import Any, Dict, Optional
from sqlalchemy.orm import Session
from app.modules.reminders import service


def _serialize_reminder(rem) -> Dict[str, Any]:
    if not rem:
        return {}
    return {
        "id": rem.id,
        "text": rem.text,
        "fire_at": rem.fire_at.isoformat() if rem.fire_at else None,
        "recurrence_rule": rem.recurrence_rule,
        "status": rem.status,
        "priority": rem.priority,
        "snoozed_until": rem.snoozed_until.isoformat() if rem.snoozed_until else None,
        "source_task_id": rem.source_task_id,
        "created_at": rem.created_at.isoformat() if rem.created_at else None,
        "fired_at": rem.fired_at.isoformat() if rem.fired_at else None,
    }


def handle_set_reminder(
    text: str,
    fire_at_str: str,
    recurrence_rule: Optional[str] = None,
    priority: str = "normal",
    source_task_id: Optional[str] = None,
    db: Optional[Session] = None,
    **kwargs
) -> Dict[str, Any]:
    if not db:
        return {"error": "Database session required"}
    rem = service.set_reminder(
        db=db,
        text=text,
        fire_at_str=fire_at_str,
        recurrence_rule=recurrence_rule,
        priority=priority,
        source_task_id=source_task_id,
    )
    return {"message": "Reminder set successfully", "reminder": _serialize_reminder(rem)}


def handle_set_alarm(
    text: str,
    fire_at_str: str,
    recurrence_rule: Optional[str] = None,
    db: Optional[Session] = None,
    **kwargs
) -> Dict[str, Any]:
    if not db:
        return {"error": "Database session required"}
    alarm = service.set_alarm(
        db=db,
        text=text,
        fire_at_str=fire_at_str,
        recurrence_rule=recurrence_rule,
    )
    return {"message": "Alarm set successfully", "alarm": _serialize_reminder(alarm)}


def handle_list_reminders(
    status: str = "pending",
    priority: Optional[str] = None,
    limit: int = 50,
    db: Optional[Session] = None,
    **kwargs
) -> Dict[str, Any]:
    if not db:
        return {"error": "Database session required"}
    reminders = service.list_reminders(db=db, status=status, priority=priority, limit=limit)
    return {
        "count": len(reminders),
        "status": status,
        "reminders": [_serialize_reminder(r) for r in reminders]
    }


def handle_cancel_reminder(
    reminder_id_or_text: str,
    db: Optional[Session] = None,
    **kwargs
) -> Dict[str, Any]:
    if not db:
        return {"error": "Database session required"}
    ok = service.cancel_reminder(db=db, reminder_id_or_text=reminder_id_or_text)
    if not ok:
        return {"error": f"No active reminder found matching '{reminder_id_or_text}'"}
    return {"message": f"Reminder matching '{reminder_id_or_text}' cancelled successfully"}


def handle_snooze_reminder(
    reminder_id_or_text: str,
    snooze_duration_str: str = "10 mins",
    db: Optional[Session] = None,
    **kwargs
) -> Dict[str, Any]:
    if not db:
        return {"error": "Database session required"}
    rem = service.snooze_reminder(
        db=db,
        reminder_id_or_text=reminder_id_or_text,
        snooze_duration_str=snooze_duration_str
    )
    if not rem:
        return {"error": f"No reminder found matching '{reminder_id_or_text}'"}
    return {"message": f"Reminder snoozed for {snooze_duration_str}", "reminder": _serialize_reminder(rem)}


TOOLS = [
    {
        "type": "function",
        "function": {
            "name": "set_reminder",
            "description": "Set a push notification reminder for a specific date or relative time.",
            "parameters": {
                "type": "object",
                "properties": {
                    "text": {"type": "string", "description": "What to remind the user about"},
                    "fire_at_str": {"type": "string", "description": "Natural language date/time, e.g. 'in 20 mins', 'tomorrow 7am', 'every weekday 6pm'"},
                    "recurrence_rule": {"type": "string", "description": "Optional recurrence rule, e.g. 'FREQ=DAILY'"},
                    "priority": {"type": "string", "description": "Priority level: 'normal', 'high', 'alarm'"}
                },
                "required": ["text", "fire_at_str"]
            }
        },
        "handler": handle_set_reminder
    },
    {
        "type": "function",
        "function": {
            "name": "set_alarm",
            "description": "Set a high-priority alarm with repeat-until-acknowledged behavior.",
            "parameters": {
                "type": "object",
                "properties": {
                    "text": {"type": "string", "description": "Alarm text or title"},
                    "fire_at_str": {"type": "string", "description": "Natural language alarm time, e.g. 'tomorrow 6:30am', 'every weekday 7am'"},
                    "recurrence_rule": {"type": "string", "description": "Optional recurrence rule"}
                },
                "required": ["text", "fire_at_str"]
            }
        },
        "handler": handle_set_alarm
    },
    {
        "type": "function",
        "function": {
            "name": "list_reminders",
            "description": "List reminders or alarms.",
            "parameters": {
                "type": "object",
                "properties": {
                    "status": {"type": "string", "description": "Filter status: 'pending' (default), 'fired', 'snoozed', 'cancelled', or 'all'"},
                    "priority": {"type": "string", "description": "Optional filter by priority: 'normal', 'alarm'"},
                    "limit": {"type": "integer", "description": "Maximum items to return"}
                },
                "required": []
            }
        },
        "handler": handle_list_reminders
    },
    {
        "type": "function",
        "function": {
            "name": "cancel_reminder",
            "description": "Cancel a pending reminder or alarm by ID or matching text.",
            "parameters": {
                "type": "object",
                "properties": {
                    "reminder_id_or_text": {"type": "string", "description": "Reminder ID or matching text keyword"}
                },
                "required": ["reminder_id_or_text"]
            }
        },
        "handler": handle_cancel_reminder
    },
    {
        "type": "function",
        "function": {
            "name": "snooze_reminder",
            "description": "Snooze a reminder or alarm for a given duration.",
            "parameters": {
                "type": "object",
                "properties": {
                    "reminder_id_or_text": {"type": "string", "description": "Reminder ID or matching text keyword"},
                    "snooze_duration_str": {"type": "string", "description": "Duration to snooze, e.g. '10 mins', '1 hour'"}
                },
                "required": ["reminder_id_or_text"]
            }
        },
        "handler": handle_snooze_reminder
    }
]
