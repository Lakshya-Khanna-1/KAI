from contextlib import asynccontextmanager
from fastapi import FastAPI
from sqlalchemy import text
from app.db.session import SessionLocal
from app.llm.client import ollama_client
from app.llm.registry import discover_routers

from app.logging_config import setup_logging

VERSION = "0.1.0"


async def _nightly_fact_job():
    _db = SessionLocal()
    try:
        from app.services.memory import run_nightly_fact_extraction
        await run_nightly_fact_extraction(_db)
    finally:
        _db.close()


async def _nightly_schedule_plan_job():
    _db = SessionLocal()
    try:
        from app.modules.schedule.service import generate_daily_plan
        generate_daily_plan(_db)
    finally:
        _db.close()

async def _morning_brief_job():
    _db = SessionLocal()
    try:
        from app.modules.schedule.service import send_morning_brief
        await send_morning_brief(_db)
    finally:
        _db.close()

async def _evening_checkin_job():
    _db = SessionLocal()
    try:
        from app.modules.schedule.service import send_evening_checkin
        await send_evening_checkin(_db)
    finally:
        _db.close()

async def _hourly_news_fetch_job():
    _db = SessionLocal()
    try:
        from app.modules.news.service import fetch_all_news_and_store
        await fetch_all_news_and_store(_db)
    finally:
        _db.close()

@asynccontextmanager
async def lifespan(app: FastAPI):
    setup_logging()
    from app.services.scheduler import init_scheduler, register_job
    from app.services.notify import process_retry_queue
    from app.services.backup import perform_db_backup
    from app.modules.reminders.service import check_missed_reminders
    from apscheduler.triggers.interval import IntervalTrigger
    from apscheduler.triggers.cron import CronTrigger

    init_scheduler()
    
    # Warm start voice pipeline (Silero VAD, Whisper STT, Piper/Kokoro TTS, Pedalboard FX)
    try:
        from app.services.voice.pipeline import voice_pipeline
        voice_pipeline.warm_start()
    except Exception as e:
        import logging
        logging.getLogger(__name__).error(f"Voice pipeline warm start failed: {e}")

    db = SessionLocal()
    try:
        await check_missed_reminders(db)
    finally:
        db.close()

    # Register background notification retry queue runner every 1 minute
    register_job(
        func=process_retry_queue,
        job_id="job_notification_retry_queue",
        trigger=IntervalTrigger(minutes=1),
        replace_existing=True
    )

    # Register nightly DB backup job at 2:00 AM UTC
    register_job(
        func=perform_db_backup,
        job_id="job_nightly_db_backup",
        trigger=CronTrigger(hour=2, minute=0),
        replace_existing=True
    )

    # Register nightly atomic fact extraction job at 3:00 AM UTC
    register_job(
        func=_nightly_fact_job,
        job_id="job_nightly_fact_extraction",
        trigger=CronTrigger(hour=3, minute=0),
        replace_existing=True
    )

    # Register nightly schedule plan generation at 21:00 (9:00 PM) UTC
    register_job(
        func=_nightly_schedule_plan_job,
        job_id="job_nightly_schedule_plan",
        trigger=CronTrigger(hour=21, minute=0),
        replace_existing=True
    )

    # Register morning briefing job at 7:00 AM UTC
    register_job(
        func=_morning_brief_job,
        job_id="job_morning_briefing",
        trigger=CronTrigger(hour=7, minute=0),
        replace_existing=True
    )

    # Register evening check-in job at 21:00 (9:00 PM) UTC
    register_job(
        func=_evening_checkin_job,
        job_id="job_evening_checkin",
        trigger=CronTrigger(hour=21, minute=0),
        replace_existing=True
    )

    # Register hourly news & research fetch job
    register_job(
        func=_hourly_news_fetch_job,
        job_id="job_hourly_news_fetch",
        trigger=IntervalTrigger(hours=1),
        replace_existing=True
    )

    yield


def create_app() -> FastAPI:
    from fastapi.staticfiles import StaticFiles
    from app.api.chat import router as chat_router

    app = FastAPI(title="KAI Assistant API", version=VERSION, lifespan=lifespan)

    # Include explicit API routers
    app.include_router(chat_router)

    # Auto-register module routers
    routers = discover_routers()
    for r in routers:
        app.include_router(r)

    @app.get("/health")
    async def health_check():
        db_status = "ok"
        try:
            db = SessionLocal()
            db.execute(text("SELECT 1"))
            db.close()
        except Exception as e:
            db_status = f"error: {str(e)}"

        ollama_reachable = await ollama_client.check_reachability()

        status = "ok" if db_status == "ok" else "degraded"

        return {
            "version": VERSION,
            "status": status,
            "database": db_status,
            "ollama": {
                "reachable": ollama_reachable
            }
        }

    @app.get("/models")
    async def list_models():
        models = await ollama_client.list_models()
        return {"models": models}

    # Serve PWA index.html at root /
    import os
    from fastapi.responses import FileResponse
    static_dir = os.path.join(os.path.dirname(__file__), "static")

    @app.get("/")
    async def read_index():
        index_path = os.path.join(static_dir, "index.html")
        if os.path.exists(index_path):
            return FileResponse(index_path)
        return {"message": "KAI API running"}

    # Mount static assets for css, js, sw.js, manifest.json
    if os.path.exists(static_dir):
        app.mount("/", StaticFiles(directory=static_dir, html=True), name="static")

    return app


app = create_app()
