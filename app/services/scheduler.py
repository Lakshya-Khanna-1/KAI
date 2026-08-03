import logging
from typing import Any, Callable, Dict, List, Optional
from apscheduler.jobstores.sqlalchemy import SQLAlchemyJobStore
from apscheduler.schedulers.background import BackgroundScheduler
from apscheduler.triggers.date import DateTrigger
from apscheduler.triggers.cron import CronTrigger
from sqlalchemy.orm import Session

from app.config import settings

logger = logging.getLogger(__name__)

_scheduler: Optional[BackgroundScheduler] = None


def get_jobstores() -> Dict[str, Any]:
    """Returns SQLAlchemyJobStore configured with main database URL."""
    return {
        "default": SQLAlchemyJobStore(url=settings.DATABASE_URL)
    }


def get_job_defaults() -> Dict[str, Any]:
    """Configures job defaults: misfire grace time (1 hour = 3600s), max instances = 3."""
    return {
        "misfire_grace_time": 3600,
        "coalesce": True,
        "max_instances": 3
    }


def init_scheduler() -> BackgroundScheduler:
    """Initializes and starts the global APScheduler instance."""
    global _scheduler
    if _scheduler is not None and _scheduler.running:
        return _scheduler

    logger.info("Initializing APScheduler with SQLAlchemyJobStore...")
    _scheduler = BackgroundScheduler(
        jobstores=get_jobstores(),
        job_defaults=get_job_defaults(),
        timezone=settings.KAI_TZ
    )
    _scheduler.start()
    logger.info("APScheduler started successfully.")
    return _scheduler


def get_scheduler() -> BackgroundScheduler:
    """Returns running scheduler instance, initializing if needed."""
    global _scheduler
    if _scheduler is None or not _scheduler.running:
        return init_scheduler()
    return _scheduler


def register_job(
    func: Callable,
    job_id: str,
    trigger: Any,
    args: Optional[List[Any]] = None,
    kwargs: Optional[Dict[str, Any]] = None,
    replace_existing: bool = True
) -> Any:
    """
    Generic job registration API for any module to schedule cron/date tasks.
    Survives application restarts via SQLAlchemyJobStore.
    """
    sched = get_scheduler()
    job = sched.add_job(
        func,
        trigger=trigger,
        id=job_id,
        args=args or [],
        kwargs=kwargs or {},
        replace_existing=replace_existing
    )
    logger.info(f"Registered job '{job_id}' with trigger {trigger}")
    return job


def remove_job(job_id: str) -> bool:
    """Removes a scheduled job by job ID."""
    sched = get_scheduler()
    if sched.get_job(job_id):
        sched.remove_job(job_id)
        logger.info(f"Removed job '{job_id}'")
        return True
    return False
