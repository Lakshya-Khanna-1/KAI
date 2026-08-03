import asyncio
import logging
import re
from datetime import datetime, timedelta, timezone
from typing import List, Optional, Tuple
from dateutil import rrule
from apscheduler.triggers.date import DateTrigger
from sqlalchemy import or_
from sqlalchemy.orm import Session

from app.db.models.reminder import Reminder
from app.db.session import SessionLocal
from app.modules.tasks.service import parse_natural_date_and_rrule
from app.services import scheduler
from app.services.notify import send_notification

logger = logging.getLogger(__name__)


def parse_snooze_duration(snooze_str: str) -> timedelta:
    """Parses snooze duration string like '10 mins', '30 minutes', '1 hour'."""
    s = snooze_str.lower().strip()
    m = re.search(r"(\d+)\s*(min|minute|hour|day)s?", s)
    if not m:
        return timedelta(minutes=10)

    val = int(m.group(1))
    unit = m.group(2)
    if "min" in unit:
        return timedelta(minutes=val)
    elif "hour" in unit:
        return timedelta(hours=val)
    elif "day" in unit:
        return timedelta(days=val)
    return timedelta(minutes=10)


def execute_reminder_fire_sync(reminder_id: str):
    """Bridge for APScheduler sync/async callback to trigger reminder execution."""
    try:
        loop = asyncio.get_running_loop()
    except RuntimeError:
        loop = None

    if loop and loop.is_running():
        asyncio.create_task(execute_reminder_fire(reminder_id))
    else:
        asyncio.run(execute_reminder_fire(reminder_id))


async def execute_reminder_fire(reminder_id: str):
    """
    Callback triggered by APScheduler when a reminder/alarm is due.
    1. Loads reminder record.
    2. Sends push notification.
    3. Updates status to 'fired' and sets fired_at.
    4. Handles alarm repeat behavior or recurring spawns.
    """
    db = SessionLocal()
    try:
        rem = db.query(Reminder).filter(Reminder.id == reminder_id).first()
        if not rem or rem.status in ("cancelled", "acked"):
            return

        now_utc = datetime.now(timezone.utc)

        # Check if fired because of snooze
        is_snoozed = rem.status == "snoozed"
        title = "KAI Alarm ⏰" if rem.priority == "alarm" else "KAI Reminder 🔔"
        if is_snoozed:
            title += " (Snoozed)"

        # Send push notification
        await send_notification(title=title, message=rem.text, priority=rem.priority)

        rem.status = "fired"
        rem.fired_at = now_utc

        # Handle alarm repeat-until-acked (repeat in 5 mins if alarm)
        if rem.priority == "alarm":
            repeat_fire_at = now_utc + timedelta(minutes=5)
            repeat_job_id = f"job_alarm_repeat_{rem.id}"
            scheduler.register_job(
                func=execute_reminder_fire_sync,
                job_id=repeat_job_id,
                trigger=DateTrigger(run_date=repeat_fire_at),
                args=[rem.id]
            )
            logger.info(f"Scheduled alarm repeat job '{repeat_job_id}' for {repeat_fire_at}")

        # Handle recurring reminder spawning
        if rem.recurrence_rule:
            try:
                dtstart = rem.fire_at or now_utc
                dtstart_naive = dtstart.astimezone(timezone.utc).replace(tzinfo=None) if dtstart.tzinfo else dtstart
                now_naive = now_utc.astimezone(timezone.utc).replace(tzinfo=None)

                rule = rrule.rrulestr(rem.recurrence_rule, dtstart=dtstart_naive)
                next_due_naive = rule.after(now_naive)
                if next_due_naive:
                    next_due_utc = next_due_naive.replace(tzinfo=timezone.utc)
                    next_rem = Reminder(
                        text=rem.text,
                        fire_at=next_due_utc,
                        recurrence_rule=rem.recurrence_rule,
                        status="pending",
                        priority=rem.priority,
                        source_task_id=rem.source_task_id,
                    )
                    db.add(next_rem)
                    db.commit()
                    db.refresh(next_rem)

                    # Schedule APScheduler job for next recurring reminder
                    scheduler.register_job(
                        func=execute_reminder_fire_sync,
                        job_id=f"job_reminder_{next_rem.id}",
                        trigger=DateTrigger(run_date=next_due_utc),
                        args=[next_rem.id]
                    )
            except Exception as err:
                logger.error(f"Error calculating recurring reminder for {rem.id}: {err}")

        db.commit()
    except Exception as err:
        logger.error(f"Error executing reminder fire for {reminder_id}: {err}", exc_info=True)
    finally:
        db.close()


async def check_missed_reminders(db: Session):
    """
    On boot, check for reminders that misfired while server was off.
    Fires a late notification and marks them fired.
    """
    now_utc = datetime.now(timezone.utc)
    missed = (
        db.query(Reminder)
        .filter(Reminder.status.in_(["pending", "snoozed"]))
        .filter(Reminder.fire_at < now_utc)
        .all()
    )

    for rem in missed:
        logger.warning(f"Misfired reminder detected on boot: '{rem.text}' (due {rem.fire_at})")
        await send_notification(
            title="KAI [MISSED REMINDER] ⚠️",
            message=f"Missed reminder: {rem.text} (was set for {rem.fire_at.strftime('%Y-%m-%d %H:%M')})",
            priority=rem.priority
        )
        rem.status = "fired"
        rem.fired_at = now_utc

    if missed:
        db.commit()


def set_reminder(
    db: Session,
    text: str,
    fire_at_str: str,
    recurrence_rule: Optional[str] = None,
    priority: str = "normal",
    source_task_id: Optional[str] = None,
) -> Reminder:
    """Create a new reminder and schedule it with APScheduler."""
    fire_at, parsed_rrule = parse_natural_date_and_rrule(fire_at_str)
    if not fire_at:
        # Fallback to in 5 minutes if parsing failed
        fire_at = datetime.now(timezone.utc) + timedelta(minutes=5)

    final_rrule = recurrence_rule or parsed_rrule

    rem = Reminder(
        text=text.strip(),
        fire_at=fire_at,
        recurrence_rule=final_rrule,
        status="pending",
        priority=priority.lower(),
        source_task_id=source_task_id,
    )
    db.add(rem)
    db.commit()
    db.refresh(rem)

    # Schedule with APScheduler
    scheduler.register_job(
        func=execute_reminder_fire_sync,
        job_id=f"job_reminder_{rem.id}",
        trigger=DateTrigger(run_date=fire_at),
        args=[rem.id]
    )

    return rem


def set_alarm(
    db: Session,
    text: str,
    fire_at_str: str,
    recurrence_rule: Optional[str] = None,
) -> Reminder:
    """Convenience wrapper for high-priority alarms with repeat-until-acked behavior."""
    return set_reminder(
        db=db,
        text=text,
        fire_at_str=fire_at_str,
        recurrence_rule=recurrence_rule,
        priority="alarm"
    )


def list_reminders(
    db: Session,
    status: str = "pending",
    priority: Optional[str] = None,
    limit: int = 50,
) -> List[Reminder]:
    """List reminders filtered by status and optional priority."""
    query = db.query(Reminder)
    if status != "all":
        query = query.filter(Reminder.status == status)

    if priority:
        query = query.filter(Reminder.priority == priority.lower())

    return query.order_by(Reminder.fire_at.asc()).limit(limit).all()


def cancel_reminder(db: Session, reminder_id_or_text: str) -> bool:
    """Cancel a reminder by ID or matching text."""
    rem = (
        db.query(Reminder)
        .filter(or_(Reminder.id == reminder_id_or_text, Reminder.text.ilike(f"%{reminder_id_or_text}%")))
        .filter(Reminder.status.in_(["pending", "snoozed"]))
        .first()
    )

    if not rem:
        return False

    rem.status = "cancelled"
    db.commit()

    # Remove jobs from scheduler
    scheduler.remove_job(f"job_reminder_{rem.id}")
    scheduler.remove_job(f"job_alarm_repeat_{rem.id}")
    return True


def snooze_reminder(db: Session, reminder_id_or_text: str, snooze_duration_str: str = "10 mins") -> Optional[Reminder]:
    """Snooze a pending or fired reminder for a specified duration."""
    rem = (
        db.query(Reminder)
        .filter(or_(Reminder.id == reminder_id_or_text, Reminder.text.ilike(f"%{reminder_id_or_text}%")))
        .first()
    )

    if not rem:
        return None

    duration = parse_snooze_duration(snooze_duration_str)
    new_fire_at = datetime.now(timezone.utc) + duration

    rem.status = "snoozed"
    rem.snoozed_until = new_fire_at
    rem.fire_at = new_fire_at
    db.commit()
    db.refresh(rem)

    # Cancel repeat alarm job if any
    scheduler.remove_job(f"job_alarm_repeat_{rem.id}")

    # Reschedule main reminder job
    scheduler.register_job(
        func=execute_reminder_fire_sync,
        job_id=f"job_reminder_{rem.id}",
        trigger=DateTrigger(run_date=new_fire_at),
        args=[rem.id]
    )

    return rem


def ack_alarm(db: Session, reminder_id_or_text: str) -> Optional[Reminder]:
    """Acknowledge an alarm to stop repeat notifications."""
    rem = (
        db.query(Reminder)
        .filter(or_(Reminder.id == reminder_id_or_text, Reminder.text.ilike(f"%{reminder_id_or_text}%")))
        .first()
    )
    if not rem:
        return None

    rem.status = "acked"
    db.commit()
    db.refresh(rem)

    scheduler.remove_job(f"job_reminder_{rem.id}")
    scheduler.remove_job(f"job_alarm_repeat_{rem.id}")
    return rem
