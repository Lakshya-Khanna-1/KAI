import logging
from typing import Dict, Any, Optional, List
from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
from sqlalchemy.orm import Session

from app.db.session import get_db
from app.modules.gym import service as gym_service

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/gym", tags=["gym"])

class LogWorkoutRequest(BaseModel):
    split_name: str = "General Workout"
    sets_text: str
    duration_min: Optional[int] = None
    notes: Optional[str] = None

class LogSetRequest(BaseModel):
    exercise: str
    weight_kg: float
    reps: int
    rpe: Optional[float] = None

class LogBodyMetricRequest(BaseModel):
    weight_kg: float
    body_fat_pct: Optional[float] = None

@router.post("/workout")
def log_workout(req: LogWorkoutRequest, db: Session = Depends(get_db)):
    parsed_sets = gym_service.parse_conversational_sets(req.sets_text)
    res = gym_service.create_workout_with_sets(
        db,
        split_name=req.split_name,
        sets_data=parsed_sets,
        duration_min=req.duration_min,
        notes=req.notes
    )
    return {"status": "success", "workout": res}

@router.post("/set")
def log_set(req: LogSetRequest, db: Session = Depends(get_db)):
    # Find latest workout session or create
    latest_w = gym_service.create_workout_with_sets(
        db,
        split_name="Quick Logging",
        sets_data=[{
            "exercise": req.exercise,
            "weight_kg": req.weight_kg,
            "reps": req.reps,
            "rpe": req.rpe
        }]
    )
    return {"status": "success", "result": latest_w}

@router.get("/prs")
def get_prs(db: Session = Depends(get_db)):
    stats = gym_service.get_gym_stats(db)
    return {"status": "success", "prs": stats["prs"]}

@router.get("/history")
def get_history(limit: int = 10, db: Session = Depends(get_db)):
    stats = gym_service.get_gym_stats(db)
    return {"status": "success", "stats": stats}

@router.post("/body")
def log_body_metric(req: LogBodyMetricRequest, db: Session = Depends(get_db)):
    bm = gym_service.log_body_metric(db, req.weight_kg, req.body_fat_pct)
    return {"status": "success", "metric_id": bm.id, "weight_kg": bm.weight_kg}

@router.get("/stats")
def get_gym_stats(db: Session = Depends(get_db)):
    stats = gym_service.get_gym_stats(db)
    return {"status": "success", "stats": stats}
