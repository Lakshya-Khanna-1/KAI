from typing import List, Optional
from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.orm import Session

from app.db.session import get_db
from app.modules.tasks.models import TaskCreate, TaskResponse, TaskUpdate
from app.modules.tasks import service

router = APIRouter(prefix="/tasks", tags=["tasks"])


@router.post("", response_model=TaskResponse)
def create_task(payload: TaskCreate, db: Session = Depends(get_db)):
    task = service.add_task(
        db=db,
        title=payload.title,
        notes=payload.notes,
        due_date_str=payload.due_date_str,
        priority=payload.priority,
        project=payload.project,
        recurrence_rule=payload.recurrence_rule,
    )
    return task


@router.get("", response_model=List[TaskResponse])
def get_tasks(
    status: str = Query("open", description="Task status: open, completed, or all"),
    project: Optional[str] = Query(None, description="Filter by project name"),
    limit: int = Query(50, ge=1, le=200),
    db: Session = Depends(get_db)
):
    return service.list_tasks(db=db, status=status, project=project, limit=limit)


@router.get("/search", response_model=List[TaskResponse])
def search_tasks(q: str = Query(..., description="Search term"), db: Session = Depends(get_db)):
    return service.search_tasks(db=db, query=q)


@router.post("/{task_id}/complete", response_model=TaskResponse)
def complete_task(task_id: str, db: Session = Depends(get_db)):
    task, _ = service.complete_task(db=db, task_id_or_title=task_id)
    if not task:
        raise HTTPException(status_code=404, detail="Task not found or already completed")
    return task


@router.patch("/{task_id}", response_model=TaskResponse)
def update_task(task_id: str, payload: TaskUpdate, db: Session = Depends(get_db)):
    task = service.update_task(
        db=db,
        task_id_or_title=task_id,
        title=payload.title,
        notes=payload.notes,
        due_date_str=payload.due_date_str,
        priority=payload.priority,
        project=payload.project,
        status=payload.status,
        recurrence_rule=payload.recurrence_rule,
    )
    if not task:
        raise HTTPException(status_code=404, detail="Task not found")
    return task


@router.delete("/{task_id}")
def delete_task(task_id: str, db: Session = Depends(get_db)):
    ok = service.delete_task(db=db, task_id_or_title=task_id)
    if not ok:
        raise HTTPException(status_code=404, detail="Task not found")
    return {"message": "Task deleted successfully"}
