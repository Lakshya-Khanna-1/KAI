from datetime import datetime, timezone
from typing import Optional
from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.orm import Session
from pydantic import BaseModel

from app.db.session import get_db
from app.db.models.schedule import ScheduleBlock
from app.modules.schedule import service as schedule_service

router = APIRouter(prefix="/schedule", tags=["schedule"])

class AddBlockRequest(BaseModel):
    title: str
    start_time: str
    end_time: str
    date_str: Optional[str] = None
    block_type: Optional[str] = "routine"
    locked: Optional[bool] = False

class UpdateBlockRequest(BaseModel):
    status: Optional[str] = None
    start_time: Optional[str] = None
    end_time: Optional[str] = None

@router.get("/today")
def get_today_schedule(db: Session = Depends(get_db)):
    date_str = datetime.now(timezone.utc).strftime("%Y-%m-%d")
    blocks = db.query(ScheduleBlock).filter(
        ScheduleBlock.date == date_str,
        ScheduleBlock.status != "cancelled"
    ).order_by(ScheduleBlock.start_at.asc()).all()

    return {
        "status": "success",
        "date": date_str,
        "blocks": [
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

@router.get("/date/{date_str}")
def get_schedule_by_date(date_str: str, db: Session = Depends(get_db)):
    blocks = db.query(ScheduleBlock).filter(
        ScheduleBlock.date == date_str,
        ScheduleBlock.status != "cancelled"
    ).order_by(ScheduleBlock.start_at.asc()).all()

    return {
        "status": "success",
        "date": date_str,
        "blocks": [
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

@router.post("/plan")
def generate_plan(date_str: Optional[str] = None, db: Session = Depends(get_db)):
    if date_str:
        target_date = datetime.strptime(date_str, "%Y-%m-%d").replace(tzinfo=timezone.utc)
    else:
        target_date = datetime.now(timezone.utc)
    plan = schedule_service.generate_daily_plan(db, target_date)
    return {"status": "success", "plan": plan}

@router.post("/block")
def add_schedule_block(req: AddBlockRequest, db: Session = Depends(get_db)):
    date_str = req.date_str or datetime.now(timezone.utc).strftime("%Y-%m-%d")
    dt_base = datetime.strptime(date_str, "%Y-%m-%d").replace(tzinfo=timezone.utc)
    sh, sm = map(int, req.start_time.split(":"))
    eh, em = map(int, req.end_time.split(":"))

    b_start = dt_base.replace(hour=sh, minute=sm)
    b_end = dt_base.replace(hour=eh, minute=em)

    block = ScheduleBlock(
        date=date_str,
        start_at=b_start,
        end_at=b_end,
        type=req.block_type or "routine",
        title=req.title,
        locked=req.locked or False
    )
    db.add(block)
    db.commit()
    db.refresh(block)

    return {"status": "success", "block_id": block.id, "title": block.title}

@router.patch("/block/{block_id}")
def update_schedule_block(block_id: str, req: UpdateBlockRequest, db: Session = Depends(get_db)):
    block = db.query(ScheduleBlock).filter(ScheduleBlock.id == block_id).first()
    if not block:
        raise HTTPException(status_code=404, detail="Block not found")

    if req.status:
        block.status = req.status
        if req.status == "completed":
            block.actual_end = datetime.now(timezone.utc)

    if req.start_time and req.end_time:
        dt_base = datetime.strptime(block.date, "%Y-%m-%d").replace(tzinfo=timezone.utc)
        sh, sm = map(int, req.start_time.split(":"))
        eh, em = map(int, req.end_time.split(":"))
        block.start_at = dt_base.replace(hour=sh, minute=sm)
        block.end_at = dt_base.replace(hour=eh, minute=em)

    db.commit()
    return {"status": "success", "block_id": block.id, "new_status": block.status}

@router.get("/free")
def get_free_time(date_str: Optional[str] = None, db: Session = Depends(get_db)):
    if not date_str:
        date_str = datetime.now(timezone.utc).strftime("%Y-%m-%d")
    return schedule_service.find_free_windows(db, date_str)

@router.post("/briefing/morning")
async def trigger_morning_briefing(db: Session = Depends(get_db)):
    msg = await schedule_service.send_morning_brief(db)
    return {"status": "success", "message_sent": msg}

@router.post("/briefing/evening")
async def trigger_evening_checkin(db: Session = Depends(get_db)):
    msg = await schedule_service.send_evening_checkin(db)
    return {"status": "success", "message_sent": msg}
