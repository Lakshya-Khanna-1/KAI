import json
from typing import Any, Dict, List, Optional
from app.db.session import SessionLocal
from app.db.models.gym import Workout, ExerciseSet, ExercisePR
from app.modules.gym import service as gym_service

async def handle_log_workout(split_name: str, sets_text: str, duration_min: Optional[int] = None, notes: Optional[str] = None) -> Dict[str, Any]:
    db = SessionLocal()
    try:
        parsed_sets = gym_service.parse_conversational_sets(sets_text)
        res = gym_service.create_workout_with_sets(
            db,
            split_name=split_name,
            sets_data=parsed_sets,
            duration_min=duration_min,
            notes=notes
        )
        return {
            "status": "success",
            "message": f"Logged workout '{split_name}' with {res['total_sets']} sets.",
            "workout_id": res["workout_id"],
            "pr_notifications": res["pr_notifications"]
        }
    finally:
        db.close()

async def handle_log_set(exercise: str, weight_kg: float, reps: int, rpe: Optional[float] = None) -> Dict[str, Any]:
    db = SessionLocal()
    try:
        # Find or create today's workout session
        latest_w = db.query(Workout).order_by(Workout.date.desc()).first()
        if not latest_w:
            latest_w = Workout(split_name="General Training", date=gym_service.now_utc())
            db.add(latest_w)
            db.commit()
            db.refresh(latest_w)

        norm_ex = gym_service.normalize_exercise_name(exercise)
        es = ExerciseSet(
            workout_id=latest_w.id,
            exercise=norm_ex,
            reps=reps,
            weight_kg=weight_kg,
            rpe=rpe
        )
        db.add(es)
        db.commit()
        db.refresh(es)

        pr_res = gym_service.check_and_update_pr(db, norm_ex, weight_kg, reps)
        epley_1rm = gym_service.calculate_epley_1rm(weight_kg, reps)

        msg = f"Logged set: {norm_ex} {reps} reps @ {weight_kg}kg (Est 1RM: {epley_1rm}kg)."
        if pr_res["is_pr"]:
            msg += f" 🎉 NEW PR DETECTED! Old 1RM: {pr_res['old_1rm']}kg -> New 1RM: {pr_res['new_1rm']}kg."

        return {
            "status": "success",
            "message": msg,
            "set_id": es.id,
            "pr_info": pr_res
        }
    finally:
        db.close()

async def handle_get_pr(exercise: str) -> Dict[str, Any]:
    db = SessionLocal()
    try:
        norm_ex = gym_service.normalize_exercise_name(exercise)
        pr = db.query(ExercisePR).filter(ExercisePR.exercise == norm_ex).first()
        if not pr:
            return {"status": "success", "message": f"No PR recorded for '{norm_ex}' yet."}
        return {
            "status": "success",
            "exercise": pr.exercise,
            "best_weight_kg": pr.best_weight,
            "best_reps": pr.best_reps,
            "est_1rm": pr.est_1rm,
            "achieved_on": pr.achieved_on.isoformat() if pr.achieved_on else None
        }
    finally:
        db.close()

async def handle_workout_history(limit: int = 5) -> Dict[str, Any]:
    db = SessionLocal()
    try:
        workouts = db.query(Workout).order_by(Workout.date.desc()).limit(limit).all()
        result = []
        for w in workouts:
            sets_data = [
                {
                    "exercise": s.exercise,
                    "reps": s.reps,
                    "weight_kg": s.weight_kg,
                    "rpe": s.rpe
                }
                for s in w.sets
            ]
            result.append({
                "id": w.id,
                "date": w.date.isoformat() if w.date else None,
                "split_name": w.split_name,
                "duration_min": w.duration_min,
                "total_sets": len(sets_data),
                "sets": sets_data
            })
        return {"status": "success", "workouts": result}
    finally:
        db.close()

async def handle_suggest_progression(exercise: str) -> Dict[str, Any]:
    db = SessionLocal()
    try:
        suggestion = gym_service.suggest_progression(db, exercise)
        stall = gym_service.check_exercise_stall(db, exercise)
        return {
            "status": "success",
            "suggestion": suggestion,
            "stall_info": stall
        }
    finally:
        db.close()

async def handle_log_body_metric(weight_kg: float, body_fat_pct: Optional[float] = None) -> Dict[str, Any]:
    db = SessionLocal()
    try:
        bm = gym_service.log_body_metric(db, weight_kg, body_fat_pct)
        return {
            "status": "success",
            "message": f"Logged body metric: {bm.weight_kg}kg" + (f" ({bm.body_fat_pct}% body fat)" if bm.body_fat_pct else ""),
            "metric_id": bm.id
        }
    finally:
        db.close()

async def handle_gym_stats() -> Dict[str, Any]:
    db = SessionLocal()
    try:
        stats = gym_service.get_gym_stats(db)
        return {"status": "success", "stats": stats}
    finally:
        db.close()

TOOLS = [
    {
        "type": "function",
        "function": {
            "name": "log_workout",
            "description": "Log a complete workout session with conversational set entries (e.g. bench 3x8 at 60).",
            "parameters": {
                "type": "object",
                "properties": {
                    "split_name": {"type": "string", "description": "Workout split name (e.g. Push, Pull, Legs)"},
                    "sets_text": {"type": "string", "description": "Conversational sets e.g. 'bench 3x8 at 60\\nsquat 5x5 at 100'"},
                    "duration_min": {"type": "integer"},
                    "notes": {"type": "string"}
                },
                "required": ["split_name", "sets_text"]
            }
        },
        "handler": handle_log_workout
    },
    {
        "type": "function",
        "function": {
            "name": "log_set",
            "description": "Log a single exercise set and auto-check for Personal Records (PRs).",
            "parameters": {
                "type": "object",
                "properties": {
                    "exercise": {"type": "string", "description": "Exercise name e.g. bench press"},
                    "weight_kg": {"type": "number", "description": "Weight lifted in kg"},
                    "reps": {"type": "integer", "description": "Number of repetitions"},
                    "rpe": {"type": "number", "description": "Optional RPE rating 1-10"}
                },
                "required": ["exercise", "weight_kg", "reps"]
            }
        },
        "handler": handle_log_set
    },
    {
        "type": "function",
        "function": {
            "name": "get_pr",
            "description": "Get the Personal Record (PR) and estimated 1RM for an exercise.",
            "parameters": {
                "type": "object",
                "properties": {
                    "exercise": {"type": "string", "description": "Exercise name e.g. bench press"}
                },
                "required": ["exercise"]
            }
        },
        "handler": handle_get_pr
    },
    {
        "type": "function",
        "function": {
            "name": "workout_history",
            "description": "Get recent workout history and logged sets.",
            "parameters": {
                "type": "object",
                "properties": {
                    "limit": {"type": "integer", "default": 5}
                }
            }
        },
        "handler": handle_workout_history
    },
    {
        "type": "function",
        "function": {
            "name": "suggest_progression",
            "description": "Get progressive overload target and stall warning for an exercise.",
            "parameters": {
                "type": "object",
                "properties": {
                    "exercise": {"type": "string", "description": "Exercise name e.g. squat"}
                },
                "required": ["exercise"]
            }
        },
        "handler": handle_suggest_progression
    },
    {
        "type": "function",
        "function": {
            "name": "log_body_metric",
            "description": "Log body weight and body fat percentage.",
            "parameters": {
                "type": "object",
                "properties": {
                    "weight_kg": {"type": "number", "description": "Body weight in kg"},
                    "body_fat_pct": {"type": "number", "description": "Body fat percentage"}
                },
                "required": ["weight_kg"]
            }
        },
        "handler": handle_log_body_metric
    },
    {
        "type": "function",
        "function": {
            "name": "gym_stats",
            "description": "Get overall gym stats including PR list, weekly volume, and bodyweight history.",
            "parameters": {"type": "object", "properties": {}}
        },
        "handler": handle_gym_stats
    }
]
