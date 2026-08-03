import json
import logging
import re
from datetime import datetime, timedelta, timezone
from typing import Dict, Any, List, Optional
from sqlalchemy.orm import Session
from sqlalchemy import func

from app.db.models.gym import Workout, ExerciseSet, BodyMetric, ExercisePR

logger = logging.getLogger(__name__)

# Basic Muscle Group Mapping for common exercises
MUSCLE_GROUPS = {
    "bench press": "Chest",
    "incline bench press": "Chest",
    "dumbbell bench press": "Chest",
    "chest flyes": "Chest",
    "pushups": "Chest",
    "squat": "Legs",
    "leg press": "Legs",
    "romanian deadlift": "Legs",
    "leg extension": "Legs",
    "leg curl": "Legs",
    "deadlift": "Back",
    "lat pulldown": "Back",
    "barbell row": "Back",
    "pullups": "Back",
    "overhead press": "Shoulders",
    "military press": "Shoulders",
    "lateral raise": "Shoulders",
    "bicep curl": "Arms",
    "tricep extension": "Arms",
    "dips": "Arms"
}

def now_utc():
    return datetime.now(timezone.utc)

def normalize_exercise_name(name: str) -> str:
    n = name.strip().lower()
    # Normalize common abbreviations
    if n in ["bench", "flat bench"]:
        return "bench press"
    if n in ["ohp", "press"]:
        return "overhead press"
    if n in ["squats"]:
        return "squat"
    if n in ["deadlifts"]:
        return "deadlift"
    if n in ["rows", "row"]:
        return "barbell row"
    return n

def calculate_epley_1rm(weight_kg: float, reps: int) -> float:
    """Calculates estimated 1RM using the Epley formula: w * (1 + r / 30)"""
    if reps <= 1:
        return float(weight_kg)
    return round(float(weight_kg) * (1.0 + float(reps) / 30.0), 2)

def parse_conversational_sets(text: str) -> List[Dict[str, Any]]:
    """
    Parses strings like:
    - "bench 3x8 at 60"
    - "squat 100kg 5x5 rpe 8"
    - "overhead press 50kg 3 sets of 10 reps"
    """
    results = []
    lines = text.strip().split("\n")

    for line in lines:
        clean = line.strip()
        if not clean:
            continue

        # Regex pattern 1: "bench press 3x8 at 60kg rpe 8" or "squat 5x5 100kg"
        m1 = re.search(r'^(.*?)\s+(\d+)\s*x\s*(\d+)(?:\s+(?:at|@))?\s+(\d+(?:\.\d+)?)\s*(?:kg|lbs)?(?:\s+rpe\s*(\d+(?:\.\d+)?))?', clean, re.IGNORECASE)
        if m1:
            ex_name = normalize_exercise_name(m1.group(1))
            num_sets = int(m1.group(2))
            reps = int(m1.group(3))
            weight = float(m1.group(4))
            rpe = float(m1.group(5)) if m1.group(5) else None

            for i in range(1, num_sets + 1):
                results.append({
                    "exercise": ex_name,
                    "set_number": i,
                    "reps": reps,
                    "weight_kg": weight,
                    "rpe": rpe
                })
            continue

        # Regex pattern 2: "bench press 60kg 3x8"
        m2 = re.search(r'^(.*?)\s+(\d+(?:\.\d+)?)\s*(?:kg|lbs)\s+(\d+)\s*x\s*(\d+)(?:\s+rpe\s*(\d+(?:\.\d+)?))?', clean, re.IGNORECASE)
        if m2:
            ex_name = normalize_exercise_name(m2.group(1))
            weight = float(m2.group(2))
            num_sets = int(m2.group(3))
            reps = int(m2.group(4))
            rpe = float(m2.group(5)) if m2.group(5) else None

            for i in range(1, num_sets + 1):
                results.append({
                    "exercise": ex_name,
                    "set_number": i,
                    "reps": reps,
                    "weight_kg": weight,
                    "rpe": rpe
                })
            continue

    return results

def check_and_update_pr(db: Session, exercise: str, weight_kg: float, reps: int) -> Dict[str, Any]:
    norm_ex = normalize_exercise_name(exercise)
    est_1rm = calculate_epley_1rm(weight_kg, reps)

    existing_pr = db.query(ExercisePR).filter(ExercisePR.exercise == norm_ex).first()
    is_new_pr = False
    old_1rm = 0.0

    if not existing_pr:
        is_new_pr = True
        pr_record = ExercisePR(
            exercise=norm_ex,
            best_weight=weight_kg,
            best_reps=reps,
            est_1rm=est_1rm,
            achieved_on=now_utc()
        )
        db.add(pr_record)
        db.commit()
    else:
        old_1rm = existing_pr.est_1rm
        if est_1rm > existing_pr.est_1rm:
            is_new_pr = True
            existing_pr.best_weight = weight_kg
            existing_pr.best_reps = reps
            existing_pr.est_1rm = est_1rm
            existing_pr.achieved_on = now_utc()
            db.commit()

    return {
        "exercise": norm_ex,
        "is_pr": is_new_pr,
        "old_1rm": old_1rm,
        "new_1rm": est_1rm,
        "weight_kg": weight_kg,
        "reps": reps
    }

def create_workout_with_sets(
    db: Session,
    split_name: Optional[str] = None,
    sets_data: Optional[List[Dict[str, Any]]] = None,
    duration_min: Optional[int] = None,
    notes: Optional[str] = None,
    energy_rating: Optional[int] = None
) -> Dict[str, Any]:
    workout = Workout(
        split_name=split_name or "General Workout",
        duration_min=duration_min,
        notes=notes,
        energy_rating=energy_rating,
        date=now_utc()
    )
    db.add(workout)
    db.commit()
    db.refresh(workout)

    pr_notifications = []
    created_sets = []

    if sets_data:
        for s in sets_data:
            ex_name = normalize_exercise_name(s.get("exercise", "Unknown"))
            es = ExerciseSet(
                workout_id=workout.id,
                exercise=ex_name,
                set_number=s.get("set_number", 1),
                reps=s.get("reps", 1),
                weight_kg=float(s.get("weight_kg", 0.0)),
                rpe=s.get("rpe")
            )
            db.add(es)
            db.commit()
            db.refresh(es)
            created_sets.append(es)

            # Check PR
            pr_res = check_and_update_pr(db, ex_name, es.weight_kg, es.reps)
            if pr_res["is_pr"]:
                pr_notifications.append(pr_res)

    return {
        "workout_id": workout.id,
        "split_name": workout.split_name,
        "total_sets": len(created_sets),
        "pr_notifications": pr_notifications
    }

def suggest_progression(db: Session, exercise: str) -> Dict[str, Any]:
    norm_ex = normalize_exercise_name(exercise)
    # Find last set for this exercise
    last_set = db.query(ExerciseSet).filter(ExerciseSet.exercise == norm_ex).order_by(ExerciseSet.id.desc()).first()

    if not last_set:
        return {
            "exercise": norm_ex,
            "has_history": False,
            "suggestion": "Start with a comfortable warm-up weight (e.g., 3 sets of 8-10 reps)."
        }

    # If last set reps >= 10, recommend weight increase (+2.5kg)
    if last_set.reps >= 10:
        rec_weight = last_set.weight_kg + 2.5
        rec_reps = 8
        reason = "You hit 10+ reps last session! Progress weight by +2.5 kg."
    else:
        rec_weight = last_set.weight_kg
        rec_reps = last_set.reps + 1
        reason = "Keep weight same, push for +1 additional rep per set."

    return {
        "exercise": norm_ex,
        "has_history": True,
        "last_session": {
            "weight_kg": last_set.weight_kg,
            "reps": last_set.reps,
            "est_1rm": calculate_epley_1rm(last_set.weight_kg, last_set.reps)
        },
        "target": {
            "weight_kg": rec_weight,
            "reps": rec_reps
        },
        "suggestion": reason
    }

def check_exercise_stall(db: Session, exercise: str) -> Dict[str, Any]:
    norm_ex = normalize_exercise_name(exercise)
    # Get last 3 distinct workouts containing this exercise
    sets = db.query(ExerciseSet).filter(ExerciseSet.exercise == norm_ex).order_by(ExerciseSet.id.desc()).limit(15).all()

    if len(sets) < 3:
        return {"exercise": norm_ex, "stalled": False, "reason": "Fewer than 3 logging entries."}

    # Track top weight per session
    top_weights = [s.weight_kg for s in sets[:3]]
    if len(set(top_weights)) == 1:
        return {
            "exercise": norm_ex,
            "stalled": True,
            "consecutive_sessions": 3,
            "weight_kg": top_weights[0],
            "recommendation": "No weight progress in 3 consecutive sessions. Consider a 10% deload or changing your rep scheme."
        }

    return {"exercise": norm_ex, "stalled": False}

def log_body_metric(db: Session, weight_kg: float, body_fat_pct: Optional[float] = None, measurements: Optional[Dict] = None) -> BodyMetric:
    bm = BodyMetric(
        date=now_utc(),
        weight_kg=weight_kg,
        body_fat_pct=body_fat_pct,
        measurements_json=json.dumps(measurements or {})
    )
    db.add(bm)
    db.commit()
    db.refresh(bm)
    return bm

def get_gym_stats(db: Session) -> Dict[str, Any]:
    # 1. PRs list
    prs = db.query(ExercisePR).all()
    prs_data = [
        {
            "exercise": pr.exercise,
            "best_weight": pr.best_weight,
            "best_reps": pr.best_reps,
            "est_1rm": pr.est_1rm,
            "achieved_on": pr.achieved_on.isoformat() if pr.achieved_on else None
        }
        for pr in prs
    ]

    # 2. Body metrics history
    metrics = db.query(BodyMetric).order_by(BodyMetric.date.asc()).limit(30).all()
    weight_history = [
        {
            "date": m.date.strftime("%Y-%m-%d") if m.date else "",
            "weight_kg": m.weight_kg,
            "body_fat_pct": m.body_fat_pct
        }
        for m in metrics
    ]

    # 3. Weekly Muscle Group Volume (last 7 days)
    seven_days_ago = now_utc() - timedelta(days=7)
    recent_sets = db.query(ExerciseSet).join(Workout).filter(Workout.date >= seven_days_ago).all()

    volume_by_group = {"Chest": 0.0, "Back": 0.0, "Legs": 0.0, "Shoulders": 0.0, "Arms": 0.0, "Other": 0.0}
    for s in recent_sets:
        group = MUSCLE_GROUPS.get(s.exercise.lower(), "Other")
        vol = s.weight_kg * s.reps
        volume_by_group[group] = round(volume_by_group.get(group, 0.0) + vol, 1)

    return {
        "prs": prs_data,
        "weight_history": weight_history,
        "weekly_volume": volume_by_group
    }
