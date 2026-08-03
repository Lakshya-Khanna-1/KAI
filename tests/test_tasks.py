import asyncio
import uuid
import pytest
from unittest.mock import AsyncMock
from sqlalchemy.orm import Session

from app.db.models.task import Task
from app.llm.loop import run_agent_loop
from app.modules.tasks import service
from app.modules.tasks.tools import (
    handle_add_task,
    handle_complete_task,
    handle_delete_task,
    handle_list_tasks,
    handle_search_tasks,
    handle_update_task,
)


def test_service_add_task_priority_and_date(db_session: Session):
    task = service.add_task(
        db=db_session,
        title="Urgent buy milk for breakfast",
        due_date_str="tomorrow 7am",
        project="groceries"
    )
    assert task.id is not None
    assert task.title == "Urgent buy milk for breakfast"
    assert task.priority == "urgent"
    assert task.project == "groceries"
    assert task.due_at is not None
    assert task.status == "open"


def test_service_list_tasks_sorting(db_session: Session):
    # Create two tasks with different due dates
    t1 = service.add_task(db=db_session, title="Task Later", due_date_str="in 5 hours")
    t2 = service.add_task(db=db_session, title="Task Soon", due_date_str="in 10 mins")

    open_tasks = service.list_tasks(db=db_session, status="open")
    titles = [t.title for t in open_tasks]
    assert "Task Soon" in titles
    assert "Task Later" in titles
    # Soonest first
    idx_soon = titles.index("Task Soon")
    idx_later = titles.index("Task Later")
    assert idx_soon < idx_later


def test_service_complete_task_with_rrule(db_session: Session):
    task = service.add_task(
        db=db_session,
        title="Daily workout",
        due_date_str="today 6pm",
        recurrence_rule="FREQ=DAILY"
    )
    completed_task, next_task = service.complete_task(db=db_session, task_id_or_title=task.id)

    assert completed_task.status == "completed"
    assert completed_task.completed_at is not None
    assert next_task is not None
    assert next_task.status == "open"
    assert next_task.title == "Daily workout"
    assert next_task.due_at > completed_task.due_at


def test_task_tools_handlers(db_session: Session):
    # 1. Add
    res_add = handle_add_task(title="Tool test task", due_date_str="in 30 mins", db=db_session)
    assert "task" in res_add
    task_id = res_add["task"]["id"]

    # 2. List
    res_list = handle_list_tasks(status="open", db=db_session)
    assert res_list["count"] >= 1

    # 3. Update
    res_upd = handle_update_task(task_id_or_title=task_id, priority="high", db=db_session)
    assert res_upd["task"]["priority"] == "high"

    # 4. Search
    res_srch = handle_search_tasks(query="Tool test", db=db_session)
    assert res_srch["count"] >= 1

    # 5. Complete
    res_comp = handle_complete_task(task_id_or_title=task_id, db=db_session)
    assert res_comp["completed_task"]["status"] == "completed"

    # 6. Delete
    res_del = handle_delete_task(task_id_or_title=task_id, db=db_session)
    assert "deleted successfully" in res_del["message"]


def test_conversational_add_list_complete(db_session: Session):
    conv_id = str(uuid.uuid4())
    mock_llm = AsyncMock()

    # Step 1: User says "add buy organic almond milk to my list"
    mock_llm.chat_completion.side_effect = [
        # Call 1 LLM requests add_task tool
        {
            "choices": [
                {
                    "message": {
                        "role": "assistant",
                        "content": None,
                        "tool_calls": [
                            {
                                "id": "call_add_1",
                                "function": {
                                    "name": "add_task",
                                    "arguments": '{"title": "buy organic almond milk", "project": "groceries"}'
                                }
                            }
                        ]
                    }
                }
            ]
        },
        # Call 1 LLM final text response
        {
            "choices": [
                {
                    "message": {
                        "role": "assistant",
                        "content": "Added 'buy organic almond milk' to your groceries list."
                    }
                }
            ]
        },
        # Step 2: User says "list my tasks" -> calls list_tasks
        {
            "choices": [
                {
                    "message": {
                        "role": "assistant",
                        "content": None,
                        "tool_calls": [
                            {
                                "id": "call_list_1",
                                "function": {
                                    "name": "list_tasks",
                                    "arguments": '{"status": "open"}'
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
                        "content": "Here is your open task: 1. buy organic almond milk (groceries)"
                    }
                }
            ]
        },
        # Step 3: User says "complete buy organic almond milk" -> calls complete_task
        {
            "choices": [
                {
                    "message": {
                        "role": "assistant",
                        "content": None,
                        "tool_calls": [
                            {
                                "id": "call_comp_1",
                                "function": {
                                    "name": "complete_task",
                                    "arguments": '{"task_id_or_title": "buy organic almond milk"}'
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
                        "content": "Marked 'buy organic almond milk' as completed."
                    }
                }
            ]
        }
    ]

    # Run Turn 1: Add task
    resp1 = asyncio.run(run_agent_loop(conv_id, "add buy organic almond milk to my list", db=db_session, client=mock_llm))
    assert "Added 'buy organic almond milk'" in resp1

    # Verify task persisted in DB
    task_in_db = db_session.query(Task).filter(Task.title == "buy organic almond milk").first()
    assert task_in_db is not None
    assert task_in_db.status == "open"
    assert task_in_db.project == "groceries"

    # Run Turn 2: List tasks
    resp2 = asyncio.run(run_agent_loop(conv_id, "list my tasks", db=db_session, client=mock_llm))
    assert "buy organic almond milk" in resp2

    # Run Turn 3: Complete task
    resp3 = asyncio.run(run_agent_loop(conv_id, "complete buy organic almond milk", db=db_session, client=mock_llm))
    assert "completed" in resp3

    # Verify task status is now completed in DB across turns/restart
    db_session.expire_all()
    task_after = db_session.query(Task).filter(Task.id == task_in_db.id).first()
    assert task_after.status == "completed"
    assert task_after.completed_at is not None
