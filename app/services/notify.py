import json
import logging
import time
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional
import httpx

from app.config import settings
from app.db.models.notification import Notification
from app.db.session import SessionLocal

logger = logging.getLogger(__name__)

# Rate limiter state (in-memory timestamp of last sent push)
_last_push_timestamp: float = 0.0


def map_priority(priority: str) -> str:
    """
    Priority mapping:
    - alarm -> 5 (max)
    - reminder / high -> 4 (high)
    - digest / default / normal -> 3 (default)
    - low -> 2 (low)
    """
    p = priority.lower().strip()
    if p in ("alarm", "max", "urgent"):
        return "5"
    elif p in ("reminder", "high"):
        return "4"
    elif p in ("low", "min"):
        return "2"
    return "3"


def build_ntfy_actions(entity_type: Optional[str] = None, entity_id: Optional[str] = None, base_url: Optional[str] = None) -> Optional[str]:
    """
    Constructs ntfy action buttons header format:
    - Done: POST callback
    - Snooze 10m: POST callback
    - Open KAI: view action
    """
    host_url = base_url or "http://localhost:8000"
    actions = []

    if entity_id:
        done_url = f"{host_url}/notify/callback/done?entity_type={entity_type or 'reminder'}&entity_id={entity_id}"
        snooze_url = f"{host_url}/notify/callback/snooze?entity_type={entity_type or 'reminder'}&entity_id={entity_id}&duration=10m"
        actions.append(f"http, Done, {done_url}, method=POST")
        actions.append(f"http, Snooze 10m, {snooze_url}, method=POST")

    actions.append(f"view, Open KAI, {host_url}/")
    return "; ".join(actions)


async def send_notification(
    title: str,
    message: str,
    priority: str = "default",
    tags: Optional[List[str]] = None,
    click_url: Optional[str] = None,
    entity_type: Optional[str] = None,
    entity_id: Optional[str] = None,
    force: bool = False
) -> bool:
    """
    Main ntfy push notification publisher.
    Enforces rate limits (max 1 push / 30s except for alarms or force=True),
    persists events to 'notifications' DB table, and handles retry queue logic.
    """
    global _last_push_timestamp

    now_ts = time.time()
    is_alarm = priority.lower() == "alarm" or priority == "5"

    # Rate limiting: max 1 push per 30s except alarms
    if not is_alarm and not force and (now_ts - _last_push_timestamp < 30.0):
        logger.info(f"Rate limited notification '{title}'. Queuing in database.")
        _record_notification_in_db(
            title=title,
            message=message,
            priority=priority,
            tags=tags,
            click_url=click_url,
            entity_type=entity_type,
            entity_id=entity_id,
            status="pending"
        )
        return False

    db_rec = _record_notification_in_db(
        title=title,
        message=message,
        priority=priority,
        tags=tags,
        click_url=click_url,
        entity_type=entity_type,
        entity_id=entity_id,
        status="pending"
    )

    if not settings.NTFY_TOPIC:
        logger.info(f"[NOTIFY LOCAL ONLY] {title}: {message}")
        _update_notification_status(db_rec.id, status="sent")
        _last_push_timestamp = now_ts
        return True

    url = f"{settings.NTFY_URL.rstrip('/')}/{settings.NTFY_TOPIC}"
    ntfy_pri = map_priority(priority)
    tag_list = ",".join(tags or ["kai"])

    headers = {
        "Title": title,
        "Priority": ntfy_pri,
        "Tags": tag_list,
    }

    if click_url:
        headers["Click"] = click_url

    actions_header = build_ntfy_actions(entity_type=entity_type, entity_id=entity_id)
    if actions_header:
        headers["Actions"] = actions_header

    try:
        async with httpx.AsyncClient(timeout=10.0) as client:
            resp = await client.post(url, content=message.encode("utf-8"), headers=headers)
            resp.raise_for_status()
            logger.info(f"Push notification sent successfully to {url}: {title}")
            _update_notification_status(db_rec.id, status="sent")
            _last_push_timestamp = now_ts
            return True
    except Exception as err:
        logger.error(f"Failed to send push notification to {url}: {err}")
        _update_notification_status(db_rec.id, status="failed", increment_attempt=True)
        return False


def process_retry_queue():
    """Processes pending or failed notifications from the 'notifications' table."""
    db = SessionLocal()
    try:
        pending = (
            db.query(Notification)
            .filter(Notification.status.in_(["pending", "failed"]))
            .filter(Notification.attempts < 5)
            .limit(10)
            .all()
        )
        for n in pending:
            payload = json.loads(n.payload_json)
            # Re-attempt send with force=True
            import asyncio
            success = asyncio.run(
                send_notification(
                    title=payload.get("title", "KAI"),
                    message=payload.get("message", ""),
                    priority=payload.get("priority", "default"),
                    tags=payload.get("tags"),
                    click_url=payload.get("click_url"),
                    entity_type=payload.get("entity_type"),
                    entity_id=payload.get("entity_id"),
                    force=True
                )
            )
            if success:
                n.status = "sent"
                n.sent_at = datetime.now(timezone.utc)
            else:
                n.attempts += 1
                n.status = "failed"
        db.commit()
    except Exception as err:
        logger.error(f"Error processing notification retry queue: {err}")
    finally:
        db.close()


def _record_notification_in_db(
    title: str,
    message: str,
    priority: str,
    tags: Optional[List[str]],
    click_url: Optional[str],
    entity_type: Optional[str],
    entity_id: Optional[str],
    status: str
) -> Notification:
    db = SessionLocal()
    try:
        payload = {
            "title": title,
            "message": message,
            "priority": priority,
            "tags": tags or [],
            "click_url": click_url,
            "entity_type": entity_type,
            "entity_id": entity_id,
        }
        n = Notification(
            payload_json=json.dumps(payload),
            status=status,
            attempts=1 if status == "pending" else 0
        )
        db.add(n)
        db.commit()
        db.refresh(n)
        return n
    finally:
        db.close()


def _update_notification_status(notification_id: str, status: str, increment_attempt: bool = False):
    db = SessionLocal()
    try:
        n = db.query(Notification).filter(Notification.id == notification_id).first()
        if n:
            n.status = status
            if status == "sent":
                n.sent_at = datetime.now(timezone.utc)
            if increment_attempt:
                n.attempts += 1
            db.commit()
    finally:
        db.close()
