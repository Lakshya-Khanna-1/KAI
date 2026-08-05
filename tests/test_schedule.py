import pytest
from datetime import datetime, timezone, timedelta
from app.db.session import SessionLocal
from app.db.models.schedule import ScheduleBlock
from app.modules.schedule import service as schedule_service
from app.modules.schedule import tools as schedule_tools

def test_generate_daily_plan():
    db = SessionLocal()
    try:
        tomorrow = datetime.now(timezone.utc) + timedelta(days=1)
        plan = schedule_service.generate_daily_plan(db, tomorrow)
        assert "date" in plan
        assert "blocks" in plan
        assert plan["total_blocks"] >= 1
    finally:
        db.close()

def test_find_free_windows():
    db = SessionLocal()
    try:
        today_str = datetime.now(timezone.utc).strftime("%Y-%m-%d")
        res = schedule_service.find_free_windows(db, today_str, min_minutes=30)
        assert "windows" in res
        assert "human_readable" in res
    finally:
        db.close()

def test_rebalance_missed_blocks():
    db = SessionLocal()
    try:
        yesterday_str = (datetime.now(timezone.utc) - timedelta(days=1)).strftime("%Y-%m-%d")
        dt_base = datetime.strptime(yesterday_str, "%Y-%m-%d").replace(tzinfo=timezone.utc)

        missed_block = ScheduleBlock(
            date=yesterday_str,
            start_at=dt_base.replace(hour=14, minute=0),
            end_at=dt_base.replace(hour=15, minute=0),
            type="study",
            title="Missed Python Study",
            status="missed"
        )
        db.add(missed_block)
        db.commit()

        res = schedule_service.rebalance_missed_blocks(db)
        assert res["total_missed"] >= 1
        assert res["rescheduled_count"] >= 1

        db.refresh(missed_block)
        assert missed_block.status == "rescheduled"
    finally:
        db.close()

@pytest.mark.anyio
async def test_schedule_tools_end_to_end():
    # 1. Add Block
    add_res = await schedule_tools.handle_add_block(
        title="Deep Focus Coding",
        start_time="11:00",
        end_time="12:30",
        block_type="study",
        locked=True
    )
    assert add_res["status"] in ["success", "warning"]
    block_id = add_res.get("block_id")

    # 2. Get Schedule
    sched_res = await schedule_tools.handle_get_schedule()
    assert sched_res["status"] == "success"

    # 3. Find Free Time
    free_res = await schedule_tools.handle_find_free_time()
    assert free_res["status"] == "success"

    if block_id:
        # 4. Move Block
        move_res = await schedule_tools.handle_move_block(block_id, "12:00", "13:30")
        assert move_res["status"] == "success"

        # 5. Mark Block Done
        done_res = await schedule_tools.handle_mark_block_done(block_id, "completed")
        assert done_res["status"] == "success"

    # 6. Plan Day
    plan_res = await schedule_tools.handle_plan_day()
    assert plan_res["status"] == "success"
