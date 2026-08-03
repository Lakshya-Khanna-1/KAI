import re
from datetime import datetime, timedelta, timezone
from typing import List, Optional, Tuple
import zoneinfo
from dateutil import rrule
from sqlalchemy import or_
from sqlalchemy.orm import Session

from app.config import settings
from app.db.models.task import Task


def infer_priority(text: str, explicit_priority: Optional[str] = None) -> str:
    """Infer task priority from explicit input or text wording."""
    if explicit_priority and explicit_priority.lower() in ("low", "medium", "high", "urgent"):
        return explicit_priority.lower()

    text_lower = text.lower()
    if any(w in text_lower for w in ["urgent", "asap", "critical", "immediately"]):
        return "urgent"
    if any(w in text_lower for w in ["important", "high priority", "high"]):
        return "high"
    if any(w in text_lower for w in ["whenever", "someday", "low priority", "low"]):
        return "low"
    return "medium"


def parse_natural_date_and_rrule(date_str: Optional[str], tz_name: Optional[str] = None) -> Tuple[Optional[datetime], Optional[str]]:
    """
    Parses natural language date and recurrence expressions into (UTC datetime, RRULE string).
    Examples: 'tomorrow 7am', 'in 20 mins', 'every weekday 6pm', 'every day 9am', 'next Monday'.
    """
    if not date_str or not date_str.strip():
        return None, None

    s = date_str.strip().lower()
    tz_str = tz_name or settings.KAI_TZ
    try:
        user_tz = zoneinfo.ZoneInfo(tz_str)
    except Exception:
        user_tz = timezone.utc

    now_user = datetime.now(user_tz)
    rrule_str = None
    target_dt = None

    # Detect recurrence patterns
    if "every weekday" in s:
        rrule_str = "FREQ=WEEKLY;BYDAY=MO,TU,WE,TH,FR"
        s = s.replace("every weekday", "").strip()
    elif "every day" in s or "daily" in s:
        rrule_str = "FREQ=DAILY"
        s = s.replace("every day", "").replace("daily", "").strip()
    elif "every week" in s or "weekly" in s:
        rrule_str = "FREQ=WEEKLY"
        s = s.replace("every week", "").replace("weekly", "").strip()
    elif "every month" in s or "monthly" in s:
        rrule_str = "FREQ=MONTHLY"
        s = s.replace("every month", "").replace("monthly", "").strip()

    # If date_str was purely RRULE string (e.g. "FREQ=DAILY")
    if date_str.upper().startswith("FREQ="):
        return None, date_str.upper()

    # Parse relative time: "in X mins / hours / days"
    m_in = re.search(r"in\s+(\d+)\s*(min|minute|hour|day)s?", s)
    if m_in:
        val = int(m_in.group(1))
        unit = m_in.group(2)
        if "min" in unit:
            target_dt = now_user + timedelta(minutes=val)
        elif "hour" in unit:
            target_dt = now_user + timedelta(hours=val)
        elif "day" in unit:
            target_dt = now_user + timedelta(days=val)

    # Parse time of day e.g. "7am", "6:30pm", "18:00"
    hour = 9  # default default 9 AM
    minute = 0
    m_time = re.search(r"(\d{1,2})(?::(\d{2}))?\s*(am|pm)?", s)
    if m_time and not m_in:
        h = int(m_time.group(1))
        m = int(m_time.group(2)) if m_time.group(2) else 0
        ampm = m_time.group(3)
        if ampm == "pm" and h < 12:
            h += 12
        elif ampm == "am" and h == 12:
            h = 0
        hour, minute = h, m

    # Parse days: "tomorrow", "today", "next <weekday>"
    if "tomorrow" in s:
        target_date = now_user.date() + timedelta(days=1)
        target_dt = datetime(target_date.year, target_date.month, target_date.day, hour, minute, tzinfo=user_tz)
    elif "today" in s:
        target_dt = datetime(now_user.year, now_user.month, now_user.day, hour, minute, tzinfo=user_tz)
    else:
        weekdays = ["monday", "tuesday", "wednesday", "thursday", "friday", "saturday", "sunday"]
        for idx, day_name in enumerate(weekdays):
            if day_name in s:
                days_ahead = idx - now_user.weekday()
                if days_ahead <= 0:
                    days_ahead += 7
                target_date = now_user.date() + timedelta(days=days_ahead)
                target_dt = datetime(target_date.year, target_date.month, target_date.day, hour, minute, tzinfo=user_tz)
                break

    # Direct ISO/standard date parsing fallback if not matched yet
    if not target_dt and not m_in:
        try:
            # Try ISO parse
            dt_parsed = datetime.fromisoformat(date_str)
            if dt_parsed.tzinfo is None:
                dt_parsed = dt_parsed.replace(tzinfo=user_tz)
            target_dt = dt_parsed
        except Exception:
            # Fallback: if time was matched, set to target_date today or tomorrow
            if m_time:
                target_date = now_user.date()
                dt_cand = datetime(target_date.year, target_date.month, target_date.day, hour, minute, tzinfo=user_tz)
                if dt_cand < now_user:
                    dt_cand += timedelta(days=1)
                target_dt = dt_cand

    # Convert target_dt to UTC for storage
    utc_due = target_dt.astimezone(timezone.utc) if target_dt else None
    return utc_due, rrule_str


def add_task(
    db: Session,
    title: str,
    notes: Optional[str] = None,
    due_date_str: Optional[str] = None,
    priority: Optional[str] = None,
    project: Optional[str] = None,
    recurrence_rule: Optional[str] = None,
) -> Task:
    """Create a new task in the database."""
    inferred_pri = infer_priority(f"{title} {notes or ''}", priority)
    due_at, parsed_rrule = parse_natural_date_and_rrule(due_date_str)
    final_rrule = recurrence_rule or parsed_rrule

    task = Task(
        title=title.strip(),
        notes=notes.strip() if notes else None,
        priority=inferred_pri,
        due_at=due_at,
        project=project.strip() if project else None,
        status="open",
        recurrence_rule=final_rrule,
    )
    db.add(task)
    db.commit()
    db.refresh(task)
    return task


def list_tasks(
    db: Session,
    status: str = "open",
    project: Optional[str] = None,
    limit: int = 50,
) -> List[Task]:
    """
    List tasks filtered by status and optional project.
    Defaults to open tasks, sorted by due_at soonest first (nulls last) then created_at.
    """
    query = db.query(Task)
    if status != "all":
        query = query.filter(Task.status == status)

    if project:
        query = query.filter(Task.project == project)

    # Sort open items: soonest due_at first, nulls last
    tasks = (
        query.order_by(
            Task.due_at.asc().nullslast(),
            Task.created_at.asc()
        )
        .limit(limit)
        .all()
    )
    return tasks


def complete_task(db: Session, task_id_or_title: str) -> Tuple[Optional[Task], Optional[Task]]:
    """
    Mark a task as completed.
    If the task has a recurrence_rule, automatically spawn the next recurring task instance!
    Returns (completed_task, next_spawned_task).
    """
    now_utc = datetime.now(timezone.utc)
    task = (
        db.query(Task)
        .filter(or_(Task.id == task_id_or_title, Task.title.ilike(f"%{task_id_or_title}%")))
        .filter(Task.status == "open")
        .first()
    )

    if not task:
        return None, None

    task.status = "completed"
    task.completed_at = now_utc

    next_task = None
    if task.recurrence_rule:
        try:
            dtstart = task.due_at or task.created_at or now_utc
            dtstart_naive = dtstart.astimezone(timezone.utc).replace(tzinfo=None) if dtstart.tzinfo else dtstart
            now_naive = now_utc.astimezone(timezone.utc).replace(tzinfo=None)

            rule = rrule.rrulestr(task.recurrence_rule, dtstart=dtstart_naive)
            next_due_naive = rule.after(dtstart_naive)
            if next_due_naive:
                next_due = next_due_naive.replace(tzinfo=timezone.utc)
                next_task = Task(
                    title=task.title,
                    notes=task.notes,
                    priority=task.priority,
                    due_at=next_due,
                    project=task.project,
                    status="open",
                    recurrence_rule=task.recurrence_rule,
                )
                db.add(next_task)
        except Exception:
            pass

    db.commit()
    db.refresh(task)
    if next_task:
        db.refresh(next_task)

    return task, next_task


def update_task(
    db: Session,
    task_id_or_title: str,
    title: Optional[str] = None,
    notes: Optional[str] = None,
    due_date_str: Optional[str] = None,
    priority: Optional[str] = None,
    project: Optional[str] = None,
    status: Optional[str] = None,
    recurrence_rule: Optional[str] = None,
) -> Optional[Task]:
    """Update an existing task."""
    task = (
        db.query(Task)
        .filter(or_(Task.id == task_id_or_title, Task.title.ilike(f"%{task_id_or_title}%")))
        .first()
    )
    if not task:
        return None

    if title is not None:
        task.title = title.strip()
    if notes is not None:
        task.notes = notes.strip()
    if priority is not None:
        task.priority = priority.lower()
    if project is not None:
        task.project = project.strip()
    if status is not None:
        task.status = status.lower()
        if task.status == "completed" and not task.completed_at:
            task.completed_at = datetime.now(timezone.utc)
    if due_date_str is not None:
        due_at, parsed_rrule = parse_natural_date_and_rrule(due_date_str)
        task.due_at = due_at
        if parsed_rrule:
            task.recurrence_rule = parsed_rrule
    if recurrence_rule is not None:
        task.recurrence_rule = recurrence_rule

    db.commit()
    db.refresh(task)
    return task


def delete_task(db: Session, task_id_or_title: str) -> bool:
    """Delete a task from the database."""
    task = (
        db.query(Task)
        .filter(or_(Task.id == task_id_or_title, Task.title.ilike(f"%{task_id_or_title}%")))
        .first()
    )
    if not task:
        return False

    db.delete(task)
    db.commit()
    return True


def search_tasks(db: Session, query: str) -> List[Task]:
    """Search tasks by title, notes, or project name."""
    pattern = f"%{query.strip()}%"
    tasks = (
        db.query(Task)
        .filter(
            or_(
                Task.title.ilike(pattern),
                Task.notes.ilike(pattern),
                Task.project.ilike(pattern)
            )
        )
        .order_by(Task.created_at.desc())
        .all()
    )
    return tasks
