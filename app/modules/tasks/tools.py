from typing import Any, Dict, Optional
from sqlalchemy.orm import Session
from app.modules.tasks import service


def _serialize_task(task) -> Dict[str, Any]:
    if not task:
        return {}
    return {
        "id": task.id,
        "title": task.title,
        "notes": task.notes,
        "priority": task.priority,
        "due_at": task.due_at.isoformat() if task.due_at else None,
        "project": task.project,
        "status": task.status,
        "created_at": task.created_at.isoformat() if task.created_at else None,
        "completed_at": task.completed_at.isoformat() if task.completed_at else None,
        "recurrence_rule": task.recurrence_rule,
    }


def handle_add_task(
    title: str,
    notes: Optional[str] = None,
    due_date_str: Optional[str] = None,
    priority: Optional[str] = None,
    project: Optional[str] = None,
    recurrence_rule: Optional[str] = None,
    db: Optional[Session] = None,
    **kwargs
) -> Dict[str, Any]:
    if not db:
        return {"error": "Database session required"}
    task = service.add_task(
        db=db,
        title=title,
        notes=notes,
        due_date_str=due_date_str,
        priority=priority,
        project=project,
        recurrence_rule=recurrence_rule,
    )
    return {"message": "Task added successfully", "task": _serialize_task(task)}


def handle_list_tasks(
    status: str = "open",
    project: Optional[str] = None,
    limit: int = 50,
    db: Optional[Session] = None,
    **kwargs
) -> Dict[str, Any]:
    if not db:
        return {"error": "Database session required"}
    tasks = service.list_tasks(db=db, status=status, project=project, limit=limit)
    return {
        "count": len(tasks),
        "status": status,
        "tasks": [_serialize_task(t) for t in tasks]
    }


def handle_complete_task(
    task_id_or_title: str,
    db: Optional[Session] = None,
    **kwargs
) -> Dict[str, Any]:
    if not db:
        return {"error": "Database session required"}
    task, next_task = service.complete_task(db=db, task_id_or_title=task_id_or_title)
    if not task:
        return {"error": f"No open task found matching '{task_id_or_title}'"}

    res = {
        "message": f"Task '{task.title}' completed",
        "completed_task": _serialize_task(task)
    }
    if next_task:
        res["next_recurring_task"] = _serialize_task(next_task)
    return res


def handle_update_task(
    task_id_or_title: str,
    title: Optional[str] = None,
    notes: Optional[str] = None,
    due_date_str: Optional[str] = None,
    priority: Optional[str] = None,
    project: Optional[str] = None,
    status: Optional[str] = None,
    recurrence_rule: Optional[str] = None,
    db: Optional[Session] = None,
    **kwargs
) -> Dict[str, Any]:
    if not db:
        return {"error": "Database session required"}
    task = service.update_task(
        db=db,
        task_id_or_title=task_id_or_title,
        title=title,
        notes=notes,
        due_date_str=due_date_str,
        priority=priority,
        project=project,
        status=status,
        recurrence_rule=recurrence_rule,
    )
    if not task:
        return {"error": f"No task found matching '{task_id_or_title}'"}
    return {"message": "Task updated successfully", "task": _serialize_task(task)}


def handle_delete_task(
    task_id_or_title: str,
    db: Optional[Session] = None,
    **kwargs
) -> Dict[str, Any]:
    if not db:
        return {"error": "Database session required"}
    ok = service.delete_task(db=db, task_id_or_title=task_id_or_title)
    if not ok:
        return {"error": f"No task found matching '{task_id_or_title}'"}
    return {"message": f"Task matching '{task_id_or_title}' deleted successfully"}


def handle_search_tasks(
    query: str,
    db: Optional[Session] = None,
    **kwargs
) -> Dict[str, Any]:
    if not db:
        return {"error": "Database session required"}
    tasks = service.search_tasks(db=db, query=query)
    return {
        "query": query,
        "count": len(tasks),
        "tasks": [_serialize_task(t) for t in tasks]
    }


TOOLS = [
    {
        "type": "function",
        "function": {
            "name": "add_task",
            "description": "Add a new task or item to the user's todo list.",
            "parameters": {
                "type": "object",
                "properties": {
                    "title": {"type": "string", "description": "Title of the task"},
                    "notes": {"type": "string", "description": "Optional extra details or notes"},
                    "due_date_str": {"type": "string", "description": "Natural language due date, e.g. 'tomorrow 6pm', 'in 20 mins', 'every weekday 8am'"},
                    "priority": {"type": "string", "description": "Priority: 'low', 'medium', 'high', or 'urgent'"},
                    "project": {"type": "string", "description": "Optional project or folder grouping name"},
                    "recurrence_rule": {"type": "string", "description": "Optional recurrence rule, e.g. 'FREQ=DAILY'"}
                },
                "required": ["title"]
            }
        },
        "handler": handle_add_task
    },
    {
        "type": "function",
        "function": {
            "name": "list_tasks",
            "description": "List tasks from the user's todo list.",
            "parameters": {
                "type": "object",
                "properties": {
                    "status": {"type": "string", "description": "Filter by status: 'open' (default), 'completed', or 'all'"},
                    "project": {"type": "string", "description": "Optional filter by project name"},
                    "limit": {"type": "integer", "description": "Maximum number of tasks to return"}
                },
                "required": []
            }
        },
        "handler": handle_list_tasks
    },
    {
        "type": "function",
        "function": {
            "name": "complete_task",
            "description": "Mark an open task as completed by ID or title.",
            "parameters": {
                "type": "object",
                "properties": {
                    "task_id_or_title": {"type": "string", "description": "Task ID or matching title keyword"}
                },
                "required": ["task_id_or_title"]
            }
        },
        "handler": handle_complete_task
    },
    {
        "type": "function",
        "function": {
            "name": "update_task",
            "description": "Update an existing task's properties.",
            "parameters": {
                "type": "object",
                "properties": {
                    "task_id_or_title": {"type": "string", "description": "Task ID or matching title keyword"},
                    "title": {"type": "string", "description": "New title"},
                    "notes": {"type": "string", "description": "New notes"},
                    "due_date_str": {"type": "string", "description": "New due date string"},
                    "priority": {"type": "string", "description": "New priority"},
                    "project": {"type": "string", "description": "New project name"},
                    "status": {"type": "string", "description": "New status: 'open' or 'completed'"},
                    "recurrence_rule": {"type": "string", "description": "New recurrence rule"}
                },
                "required": ["task_id_or_title"]
            }
        },
        "handler": handle_update_task
    },
    {
        "type": "function",
        "function": {
            "name": "delete_task",
            "description": "Delete a task permanently by ID or title.",
            "parameters": {
                "type": "object",
                "properties": {
                    "task_id_or_title": {"type": "string", "description": "Task ID or matching title keyword"}
                },
                "required": ["task_id_or_title"]
            }
        },
        "handler": handle_delete_task
    },
    {
        "type": "function",
        "function": {
            "name": "search_tasks",
            "description": "Search tasks by title, notes, or project keywords.",
            "parameters": {
                "type": "object",
                "properties": {
                    "query": {"type": "string", "description": "Search keyword or text query"}
                },
                "required": ["query"]
            }
        },
        "handler": handle_search_tasks
    }
]
