import json
import time
from unittest.mock import AsyncMock, patch
import pytest
from fastapi.testclient import TestClient
from sqlalchemy.orm import Session

from app.db.models.notification import Notification
from app.db.models.reminder import Reminder
from app.db.models.task import Task
from app.main import app
from app.modules.reminders import service as reminder_service
from app.modules.tasks import service as task_service
from app.services import notify

client = TestClient(app)


def test_map_priority():
    assert notify.map_priority("alarm") == "5"
    assert notify.map_priority("reminder") == "4"
    assert notify.map_priority("digest") == "3"
    assert notify.map_priority("low") == "2"


def test_build_ntfy_actions():
    actions = notify.build_ntfy_actions(entity_type="reminder", entity_id="rem-123")
    assert "Done" in actions
    assert "Snooze 10m" in actions
    assert "Open KAI" in actions
    assert "rem-123" in actions


@pytest.mark.anyio
async def test_send_notification_rate_limiting(db_session: Session):
    with patch("httpx.AsyncClient.post", new_callable=AsyncMock) as mock_post:
        mock_post.return_value.status_code = 200

        # First call should succeed
        res1 = await notify.send_notification("Test 1", "Message 1", priority="normal", force=True)
        assert res1 is True

        # Second call within 30s without force should be rate-limited and queued
        res2 = await notify.send_notification("Test 2", "Message 2", priority="normal", force=False)
        assert res2 is False

        # Alarm priority bypasses rate limiting
        res_alarm = await notify.send_notification("Alarm 1", "Alarm message", priority="alarm", force=False)
        assert res_alarm is True


def test_notification_callback_done(db_session: Session):
    rem = reminder_service.set_reminder(db_session, text="Take medicine", fire_at_str="in 5 mins")

    response = client.post(f"/notify/callback/done?entity_type=reminder&entity_id={rem.id}")
    assert response.status_code == 200
    assert response.json()["status"] == "success"

    db_session.expire_all()
    rem_after = db_session.query(Reminder).filter(Reminder.id == rem.id).first()
    assert rem_after.status == "acked"


def test_notification_callback_snooze(db_session: Session):
    rem = reminder_service.set_reminder(db_session, text="Workout session", fire_at_str="in 5 mins")

    response = client.post(f"/notify/callback/snooze?entity_type=reminder&entity_id={rem.id}&duration=10m")
    assert response.status_code == 200
    assert response.json()["status"] == "success"

    db_session.expire_all()
    rem_after = db_session.query(Reminder).filter(Reminder.id == rem.id).first()
    assert rem_after.status == "snoozed"


def test_notification_test_endpoint():
    response = client.post("/notify/test", json={"title": "Custom Test", "message": "Testing 123"})
    assert response.status_code == 200
    data = response.json()
    assert data["title"] == "Custom Test"
    assert "Done" in data["actions"]
    assert "Snooze 10m" in data["actions"]
    assert "Open KAI" in data["actions"]
