from typing import Optional
from fastapi import APIRouter, Depends, HTTPException, Query, status
from pydantic import BaseModel
from sqlalchemy.orm import Session

from app.db.session import get_db
from app.modules.notifications import service
from app.services.notify import send_notification

router = APIRouter(prefix="/notify", tags=["notifications"])


class TestNotificationRequest(BaseModel):
    title: Optional[str] = "KAI Test Notification 🔔"
    message: Optional[str] = "This is a test push notification from KAI personal assistant."
    priority: Optional[str] = "normal"
    entity_id: Optional[str] = "test-entity-123"
    entity_type: Optional[str] = "reminder"


@router.post("/callback/done")
def callback_done_endpoint(
    entity_id: str = Query(..., description="ID of target task or reminder"),
    entity_type: str = Query("reminder", description="Type of entity: 'task' or 'reminder'"),
    db: Session = Depends(get_db)
):
    res = service.handle_notification_action_done(db=db, entity_type=entity_type, entity_id=entity_id)
    if res.get("status") == "error":
        raise HTTPException(status_code=404, detail=res.get("message"))
    return res


@router.post("/callback/snooze")
def callback_snooze_endpoint(
    entity_id: str = Query(..., description="ID of target reminder or alarm"),
    entity_type: str = Query("reminder", description="Type of entity"),
    duration: str = Query("10m", description="Snooze duration, e.g. 10m"),
    db: Session = Depends(get_db)
):
    res = service.handle_notification_action_snooze(db=db, entity_type=entity_type, entity_id=entity_id, duration=duration)
    if res.get("status") == "error":
        raise HTTPException(status_code=404, detail=res.get("message"))
    return res


@router.post("/test")
async def test_notification_endpoint(payload: Optional[TestNotificationRequest] = None):
    p = payload or TestNotificationRequest()
    success = await send_notification(
        title=p.title,
        message=p.message,
        priority=p.priority,
        tags=["robot", "test"],
        entity_type=p.entity_type,
        entity_id=p.entity_id,
        force=True
    )
    return {
        "status": "sent" if success else "queued_or_failed",
        "title": p.title,
        "message": p.message,
        "actions": ["Done", "Snooze 10m", "Open KAI"]
    }
