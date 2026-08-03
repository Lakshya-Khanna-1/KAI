import asyncio
import uuid
from datetime import datetime, timedelta, timezone
from unittest.mock import AsyncMock, patch
import pytest
from sqlalchemy.orm import Session

from app.db.models.reminder import Reminder
from app.llm.loop import run_agent_loop
from app.modules.reminders import service, tools


def test_service_set_reminder(db_session: Session):
    rem = service.set_reminder(
        db=db_session,
        text="Take out trash",
        fire_at_str="in 10 mins",
        priority="normal"
    )
    assert rem is not None
    assert rem.text == "Take out trash"
    assert rem.status == "pending"
    assert rem.priority == "normal"
    fire_at = rem.fire_at.replace(tzinfo=timezone.utc) if rem.fire_at.tzinfo is None else rem.fire_at
    assert fire_at > datetime.now(timezone.utc)


def test_service_set_alarm(db_session: Session):
    alarm = service.set_alarm(
        db=db_session,
        text="Wake up for workout",
        fire_at_str="tomorrow 6am"
    )
    assert alarm is not None
    assert alarm.text == "Wake up for workout"
    assert alarm.status == "pending"
    assert alarm.priority == "alarm"


def test_service_list_reminders(db_session: Session):
    rem1 = service.set_reminder(db_session, text="Water plants", fire_at_str="in 5 mins")
    rem2 = service.set_alarm(db_session, text="Morning standup", fire_at_str="in 15 mins")

    pending_list = service.list_reminders(db_session, status="pending")
    assert len(pending_list) >= 2

    alarm_list = service.list_reminders(db_session, status="pending", priority="alarm")
    assert any(r.id == rem2.id for r in alarm_list)


def test_service_snooze_reminder(db_session: Session):
    rem = service.set_reminder(db_session, text="Check oven", fire_at_str="in 2 mins")
    snoozed = service.snooze_reminder(db_session, rem.id, snooze_duration_str="15 mins")
    assert snoozed is not None
    assert snoozed.status == "snoozed"
    assert snoozed.snoozed_until is not None


def test_service_cancel_reminder(db_session: Session):
    rem = service.set_reminder(db_session, text="Cancel subscription", fire_at_str="in 30 mins")
    ok = service.cancel_reminder(db_session, rem.id)
    assert ok is True

    db_session.expire_all()
    cancelled_rem = db_session.query(Reminder).filter(Reminder.id == rem.id).first()
    assert cancelled_rem.status == "cancelled"


@pytest.mark.anyio
async def test_service_check_missed_reminders(db_session: Session):
    past_due = datetime.now(timezone.utc) - timedelta(minutes=20)
    missed_rem = Reminder(
        text="Past meeting",
        fire_at=past_due,
        status="pending",
        priority="normal"
    )
    db_session.add(missed_rem)
    db_session.commit()

    with patch("app.modules.reminders.service.send_notification", new_callable=AsyncMock) as mock_notify:
        await service.check_missed_reminders(db_session)
        assert mock_notify.called

    db_session.expire_all()
    updated = db_session.query(Reminder).filter(Reminder.id == missed_rem.id).first()
    assert updated.status == "fired"


def test_conversational_reminder_flow(db_session: Session):
    conv_id = str(uuid.uuid4())
    mock_llm = AsyncMock()

    mock_llm.chat_completion.side_effect = [
        # Call 1: Set reminder
        {
            "choices": [
                {
                    "message": {
                        "role": "assistant",
                        "content": None,
                        "tool_calls": [
                            {
                                "id": "call_rem_1",
                                "function": {
                                    "name": "set_reminder",
                                    "arguments": '{"text": "Call doctor for checkup", "fire_at_str": "tomorrow 10am"}'
                                }
                            }
                        ]
                    }
                }
            ]
        },
        {
            "choices": [
                {
                    "message": {
                        "role": "assistant",
                        "content": "Reminder set for tomorrow 10am to call doctor."
                    }
                }
            ]
        },
        # Call 2: Cancel reminder
        {
            "choices": [
                {
                    "message": {
                        "role": "assistant",
                        "content": None,
                        "tool_calls": [
                            {
                                "id": "call_rem_2",
                                "function": {
                                    "name": "cancel_reminder",
                                    "arguments": '{"reminder_id_or_text": "Call doctor"}'
                                }
                            }
                        ]
                    }
                }
            ]
        },
        {
            "choices": [
                {
                    "message": {
                        "role": "assistant",
                        "content": "Cancelled reminder to call doctor."
                    }
                }
            ]
        }
    ]

    res1 = asyncio.run(run_agent_loop(conv_id, "remind me tomorrow at 10am to call doctor", db=db_session, client=mock_llm))
    assert "Reminder set" in res1

    rem = db_session.query(Reminder).filter(Reminder.text == "Call doctor for checkup").first()
    assert rem is not None
    assert rem.status == "pending"

    res2 = asyncio.run(run_agent_loop(conv_id, "cancel my call doctor reminder", db=db_session, client=mock_llm))
    assert "Cancelled" in res2

    db_session.expire_all()
    rem_after = db_session.query(Reminder).filter(Reminder.id == rem.id).first()
    assert rem_after.status == "cancelled"
