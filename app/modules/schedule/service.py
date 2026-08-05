import json
import logging
from datetime import datetime, timedelta, timezone, time
from typing import Dict, Any, List, Optional
from sqlalchemy.orm import Session
from sqlalchemy import and_, or_

from app.config import settings
from app.db.models.schedule import ScheduleBlock, AvailabilityRule
from app.db.models.reminder import Reminder
from app.db.models.task import Task
from app.db.models.roadmap import Roadmap, RoadmapTopic, RoadmapPhase
from app.db.models.profile import Profile
from app.services import notify

logger = logging.getLogger(__name__)

def parse_time_str(t_str: str) -> time:
    parts = t_str.split(":")
    return time(int(parts[0]), int(parts[1]))

def format_time_str(dt: datetime) -> str:
    return dt.strftime("%H:%M")

def get_target_date_str(target_date: Optional[datetime] = None) -> str:
    if not target_date:
        target_date = datetime.now(timezone.utc)
    return target_date.strftime("%Y-%m-%d")

def make_utc(dt: Optional[datetime]) -> Optional[datetime]:
    if dt is None:
        return None
    if dt.tzinfo is None:
        return dt.replace(tzinfo=timezone.utc)
    return dt

def check_block_conflicts(
    db: Session,
    start_at: datetime,
    end_at: datetime,
    ignore_block_id: Optional[str] = None
) -> List[ScheduleBlock]:
    start_at = make_utc(start_at)
    end_at = make_utc(end_at)
    query = db.query(ScheduleBlock).filter(
        and_(
            ScheduleBlock.start_at < end_at,
            ScheduleBlock.end_at > start_at,
            ScheduleBlock.status != "cancelled"
        )
    )
    if ignore_block_id:
        query = query.filter(ScheduleBlock.id != ignore_block_id)
    return query.all()

def find_free_windows(
    db: Session,
    date_str: str,
    day_start_hour: int = 7,
    day_end_hour: int = 22,
    min_minutes: int = 30
) -> Dict[str, Any]:
    # Parse day boundary in UTC
    dt_base = datetime.strptime(date_str, "%Y-%m-%d").replace(tzinfo=timezone.utc)
    day_start = dt_base.replace(hour=day_start_hour, minute=0, second=0)
    day_end = dt_base.replace(hour=day_end_hour, minute=0, second=0)

    # Get scheduled blocks on this date
    blocks = db.query(ScheduleBlock).filter(
        ScheduleBlock.date == date_str,
        ScheduleBlock.status != "cancelled"
    ).order_by(ScheduleBlock.start_at.asc()).all()

    free_windows = []
    current_time = day_start

    for b in blocks:
        b_start = make_utc(b.start_at)
        b_end = make_utc(b.end_at)
        # If there is a gap before this block
        if b_start > current_time:
            gap_min = int((b_start - current_time).total_seconds() / 60)
            if gap_min >= min_minutes:
                free_windows.append({
                    "start": current_time.strftime("%H:%M"),
                    "end": b_start.strftime("%H:%M"),
                    "duration_min": gap_min
                })
        if b_end > current_time:
            current_time = b_end

    # Gap after last block
    if day_end > current_time:
        gap_min = int((day_end - current_time).total_seconds() / 60)
        if gap_min >= min_minutes:
            free_windows.append({
                "start": current_time.strftime("%H:%M"),
                "end": day_end.strftime("%H:%M"),
                "duration_min": gap_min
            })

    # Format human friendly message
    human_msgs = []
    for w in free_windows:
        start_h = datetime.strptime(w['start'], "%H:%M").strftime("%I:%M %p").lstrip("0")
        human_msgs.append(f"{w['duration_min']} free minutes after {start_h}")

    msg = ". ".join(human_msgs) if human_msgs else "No free windows available today."

    return {
        "date": date_str,
        "windows": free_windows,
        "human_readable": msg
    }

def generate_daily_plan(db: Session, target_date: Optional[datetime] = None) -> Dict[str, Any]:
    if not target_date:
        target_date = datetime.now(timezone.utc) + timedelta(days=1)  # Default tomorrow
    date_str = target_date.strftime("%Y-%m-%d")
    weekday = target_date.weekday()

    # Clear un-locked blocks for target_date to avoid duplicates
    db.query(ScheduleBlock).filter(
        ScheduleBlock.date == date_str,
        ScheduleBlock.locked == False
    ).delete()
    db.commit()

    dt_base = datetime.strptime(date_str, "%Y-%m-%d").replace(tzinfo=timezone.utc)
    new_blocks = []

    # 1. Fixed Commitments from Reminders & Tasks
    reminders = db.query(Reminder).filter(Reminder.status == "pending").all()
    for r in reminders:
        if r.fire_at and r.fire_at.strftime("%Y-%m-%d") == date_str:
            b_start = r.fire_at
            b_end = b_start + timedelta(minutes=30)
            block = ScheduleBlock(
                date=date_str,
                start_at=b_start,
                end_at=b_end,
                type="commitment",
                title=f"Reminder: {r.text}",
                linked_id=r.id,
                locked=True
            )
            db.add(block)
            db.commit()
            new_blocks.append(block)

    # 2. Gym Session (e.g. at 07:30 or 17:30)
    # Check user profile for gym preference
    gym_pref = db.query(Profile).filter(Profile.key == "gym_split").first()
    gym_title = f"Gym Workout ({gym_pref.value_json if gym_pref else 'Push/Pull/Legs'})"
    gym_start = dt_base.replace(hour=7, minute=30)
    gym_end = gym_start + timedelta(minutes=60)
    if not check_block_conflicts(db, gym_start, gym_end):
        b_gym = ScheduleBlock(
            date=date_str,
            start_at=gym_start,
            end_at=gym_end,
            type="gym",
            title=gym_title,
            locked=False
        )
        db.add(b_gym)
        db.commit()
        new_blocks.append(b_gym)

    # 3. Study Blocks from Active Roadmap
    active_rm = db.query(Roadmap).filter(Roadmap.active == True).first()
    if active_rm:
        next_topic = None
        for phase in active_rm.phases:
            for top in phase.topics:
                if top.status != "completed":
                    next_topic = top
                    break
            if next_topic:
                break

        if next_topic:
            # High energy slot (10:00 - 11:30)
            study_start1 = dt_base.replace(hour=10, minute=0)
            study_end1 = study_start1 + timedelta(minutes=90)
            if not check_block_conflicts(db, study_start1, study_end1):
                b_study1 = ScheduleBlock(
                    date=date_str,
                    start_at=study_start1,
                    end_at=study_end1,
                    type="study",
                    title=f"Roadmap Study: {next_topic.title}",
                    linked_id=next_topic.id,
                    locked=False
                )
                db.add(b_study1)
                db.commit()
                new_blocks.append(b_study1)

            # Secondary slot (14:00 - 15:30)
            study_start2 = dt_base.replace(hour=14, minute=0)
            study_end2 = study_start2 + timedelta(minutes=90)
            if not check_block_conflicts(db, study_start2, study_end2):
                b_study2 = ScheduleBlock(
                    date=date_str,
                    start_at=study_start2,
                    end_at=study_end2,
                    type="study",
                    title=f"Roadmap Review: {next_topic.title}",
                    linked_id=next_topic.id,
                    locked=False
                )
                db.add(b_study2)
                db.commit()
                new_blocks.append(b_study2)

    # 4. Buffer & Free Time Filler
    # Fetch final list of schedule blocks sorted by start time
    all_blocks = db.query(ScheduleBlock).filter(ScheduleBlock.date == date_str).order_by(ScheduleBlock.start_at.asc()).all()

    return {
        "date": date_str,
        "total_blocks": len(all_blocks),
        "blocks": [
            {
                "id": b.id,
                "title": b.title,
                "type": b.type,
                "start": b.start_at.strftime("%H:%M"),
                "end": b.end_at.strftime("%H:%M"),
                "locked": b.locked,
                "status": b.status
            }
            for b in all_blocks
        ]
    }

def rebalance_missed_blocks(db: Session) -> Dict[str, Any]:
    """Finds missed blocks and reschedules them into open slots over remaining week."""
    missed = db.query(ScheduleBlock).filter(ScheduleBlock.status == "missed").all()
    rescheduled_count = 0

    for m in missed:
        # Search next 3 days for free window
        for offset in range(1, 4):
            future_date = datetime.now(timezone.utc) + timedelta(days=offset)
            date_str = future_date.strftime("%Y-%m-%d")
            free_info = find_free_windows(db, date_str, min_minutes=45)
            if free_info["windows"]:
                win = free_info["windows"][0]
                dt_base = datetime.strptime(date_str, "%Y-%m-%d").replace(tzinfo=timezone.utc)
                sh, sm = map(int, win["start"].split(":"))
                b_start = dt_base.replace(hour=sh, minute=sm)
                b_end = b_start + timedelta(minutes=45)

                new_block = ScheduleBlock(
                    date=date_str,
                    start_at=b_start,
                    end_at=b_end,
                    type=m.type,
                    title=f"[Rebalanced] {m.title}",
                    linked_id=m.linked_id,
                    status="scheduled"
                )
                db.add(new_block)
                m.status = "rescheduled"
                db.commit()
                rescheduled_count += 1
                break

    return {
        "total_missed": len(missed),
        "rescheduled_count": rescheduled_count
    }

async def send_morning_brief(db: Session):
    today_str = datetime.now(timezone.utc).strftime("%Y-%m-%d")
    plan = generate_daily_plan(db, datetime.now(timezone.utc))

    first_block = plan["blocks"][0]["title"] if plan["blocks"] else "No scheduled blocks yet"
    free_info = find_free_windows(db, today_str)

    # Top 5 news digest for morning briefing
    from app.modules.news import service as news_service
    top_news = news_service.get_top_news_digest(db, limit=5)
    news_lines = ""
    if top_news:
        news_lines = "\n📰 Top AI News & Research:\n" + "\n".join(
            f"  - [{n['source'].upper()}] {n['title'][:60]}..." for n in top_news
        )

    msg = (
        f"☀️ Good morning! Today's Briefing ({today_str}):\n"
        f"• First activity: {first_block}\n"
        f"• Total blocks scheduled: {plan['total_blocks']}\n"
        f"• Free windows: {free_info['human_readable']}\n"
        f"• Weather: Clear Sky, 24°C"
        f"{news_lines}"
    )
    await notify.send_notification(
        title="Good Morning Briefing",
        message=msg,
        priority="default"
    )
    return msg

async def send_evening_checkin(db: Session):
    today_str = datetime.now(timezone.utc).strftime("%Y-%m-%d")
    blocks = db.query(ScheduleBlock).filter(ScheduleBlock.date == today_str).all()
    completed = [b for b in blocks if b.status == "completed"]
    missed = [b for b in blocks if b.status in ["missed", "scheduled"]]

    msg = (
        f"🌙 Evening Check-in ({today_str}):\n"
        f"• Completed: {len(completed)} blocks\n"
        f"• Pending/Slipped: {len(missed)} blocks\n"
        f"What is one wins or learning from today?"
    )
    await notify.send_notification(msg)
    return msg
