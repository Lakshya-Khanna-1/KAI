from datetime import datetime, timezone, timedelta
from typing import Optional, Dict, Any
from app.db.session import SessionLocal
from app.db.models.schedule import ScheduleBlock
from app.modules.schedule import service as schedule_service

async def handle_plan_day(date_str: Optional[str] = None) -> Dict[str, Any]:
    db = SessionLocal()
    try:
        if date_str:
            target_date = datetime.strptime(date_str, "%Y-%m-%d").replace(tzinfo=timezone.utc)
        else:
            target_date = datetime.now(timezone.utc) + timedelta(days=1)
        plan = schedule_service.generate_daily_plan(db, target_date)
        return {"status": "success", "plan": plan}
    except Exception as e:
        return {"status": "error", "message": str(e)}
    finally:
        db.close()

async def handle_get_schedule(date_str: Optional[str] = None) -> Dict[str, Any]:
    db = SessionLocal()
    try:
        if not date_str:
            date_str = datetime.now(timezone.utc).strftime("%Y-%m-%d")
        blocks = db.query(ScheduleBlock).filter(
            ScheduleBlock.date == date_str,
            ScheduleBlock.status != "cancelled"
        ).order_by(ScheduleBlock.start_at.asc()).all()

        return {
            "status": "success",
            "date": date_str,
            "count": len(blocks),
            "schedule": [
                {
                    "id": b.id,
                    "title": b.title,
                    "type": b.type,
                    "start": b.start_at.strftime("%H:%M"),
                    "end": b.end_at.strftime("%H:%M"),
                    "status": b.status,
                    "locked": b.locked
                }
                for b in blocks
            ]
        }
    finally:
        db.close()

async def handle_find_free_time(date_str: Optional[str] = None, min_minutes: int = 30) -> Dict[str, Any]:
    db = SessionLocal()
    try:
        if not date_str:
            date_str = datetime.now(timezone.utc).strftime("%Y-%m-%d")
        res = schedule_service.find_free_windows(db, date_str, min_minutes=min_minutes)
        return {"status": "success", "result": res}
    finally:
        db.close()

async def handle_add_block(
    title: str,
    start_time: str,
    end_time: str,
    date_str: Optional[str] = None,
    block_type: str = "commitment",
    locked: bool = True
) -> Dict[str, Any]:
    db = SessionLocal()
    try:
        if not date_str:
            date_str = datetime.now(timezone.utc).strftime("%Y-%m-%d")

        dt_base = datetime.strptime(date_str, "%Y-%m-%d").replace(tzinfo=timezone.utc)
        sh, sm = map(int, start_time.split(":"))
        eh, em = map(int, end_time.split(":"))

        b_start = dt_base.replace(hour=sh, minute=sm)
        b_end = dt_base.replace(hour=eh, minute=em)

        conflicts = schedule_service.check_block_conflicts(db, b_start, b_end)
        if conflicts:
            conf_titles = [c.title for c in conflicts]
            return {
                "status": "warning",
                "message": f"Conflict detected with existing blocks: {', '.join(conf_titles)}. Block added anyway.",
                "conflicts": conf_titles
            }

        block = ScheduleBlock(
            date=date_str,
            start_at=b_start,
            end_at=b_end,
            type=block_type,
            title=title,
            locked=locked
        )
        db.add(block)
        db.commit()

        return {"status": "success", "block_id": block.id, "title": block.title}
    finally:
        db.close()

async def handle_move_block(block_id: str, new_start_time: str, new_end_time: str) -> Dict[str, Any]:
    db = SessionLocal()
    try:
        block = db.query(ScheduleBlock).filter(ScheduleBlock.id == block_id).first()
        if not block:
            return {"status": "error", "message": "Block not found."}

        date_str = block.date
        dt_base = datetime.strptime(date_str, "%Y-%m-%d").replace(tzinfo=timezone.utc)
        sh, sm = map(int, new_start_time.split(":"))
        eh, em = map(int, new_end_time.split(":"))

        b_start = dt_base.replace(hour=sh, minute=sm)
        b_end = dt_base.replace(hour=eh, minute=em)

        block.start_at = b_start
        block.end_at = b_end
        db.commit()

        return {"status": "success", "block_id": block.id, "new_start": new_start_time, "new_end": new_end_time}
    finally:
        db.close()

async def handle_mark_block_done(block_id: str, status: str = "completed") -> Dict[str, Any]:
    db = SessionLocal()
    try:
        block = db.query(ScheduleBlock).filter(ScheduleBlock.id == block_id).first()
        if not block:
            return {"status": "error", "message": "Block not found."}

        block.status = status
        if status == "completed":
            block.actual_end = datetime.now(timezone.utc)
        db.commit()

        return {"status": "success", "block_id": block.id, "block_status": block.status}
    finally:
        db.close()

TOOLS = [
    {
        "type": "function",
        "function": {
            "name": "plan_day",
            "description": "Generate an adaptive daily plan for a target date (default tomorrow) balancing commitments, gym, roadmap study debt, and energy slots.",
            "parameters": {
                "type": "object",
                "properties": {
                    "date_str": {"type": "string", "description": "Target date in YYYY-MM-DD format (optional)"}
                }
            }
        },
        "handler": handle_plan_day
    },
    {
        "type": "function",
        "function": {
            "name": "get_schedule",
            "description": "Get schedule blocks for a specific date (default today).",
            "parameters": {
                "type": "object",
                "properties": {
                    "date_str": {"type": "string", "description": "Date in YYYY-MM-DD format (optional)"}
                }
            }
        },
        "handler": handle_get_schedule
    },
    {
        "type": "function",
        "function": {
            "name": "find_free_time",
            "description": "Find free unallocated time windows in today's or a target date's schedule.",
            "parameters": {
                "type": "object",
                "properties": {
                    "date_str": {"type": "string", "description": "Date in YYYY-MM-DD format (optional)"},
                    "min_minutes": {"type": "integer", "description": "Minimum duration in minutes (default 30)"}
                }
            }
        },
        "handler": handle_find_free_time
    },
    {
        "type": "function",
        "function": {
            "name": "add_block",
            "description": "Add a new fixed or flexible schedule block to a date.",
            "parameters": {
                "type": "object",
                "properties": {
                    "title": {"type": "string", "description": "Title of schedule block"},
                    "start_time": {"type": "string", "description": "Start time e.g. '14:00'"},
                    "end_time": {"type": "string", "description": "End time e.g. '15:30'"},
                    "date_str": {"type": "string", "description": "Date YYYY-MM-DD (optional, default today)"},
                    "block_type": {"type": "string", "description": "Type: commitment, gym, study, buffer, routine"},
                    "locked": {"type": "boolean", "description": "True if fixed commitment"}
                },
                "required": ["title", "start_time", "end_time"]
            }
        },
        "handler": handle_add_block
    },
    {
        "type": "function",
        "function": {
            "name": "move_block",
            "description": "Move or reschedule an existing schedule block to a new time window.",
            "parameters": {
                "type": "object",
                "properties": {
                    "block_id": {"type": "string", "description": "ID of block to move"},
                    "new_start_time": {"type": "string", "description": "New start time e.g. '16:00'"},
                    "new_end_time": {"type": "string", "description": "New end time e.g. '17:00'"}
                },
                "required": ["block_id", "new_start_time", "new_end_time"]
            }
        },
        "handler": handle_move_block
    },
    {
        "type": "function",
        "function": {
            "name": "mark_block_done",
            "description": "Mark a schedule block as completed, missed, or in progress.",
            "parameters": {
                "type": "object",
                "properties": {
                    "block_id": {"type": "string", "description": "ID of block"},
                    "status": {"type": "string", "description": "completed, missed, in_progress, scheduled"}
                },
                "required": ["block_id"]
            }
        },
        "handler": handle_mark_block_done
    }
]
