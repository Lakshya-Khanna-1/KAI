import pytest
from app.db.session import SessionLocal
from app.modules.gym import service as gym_service
from app.modules.gym import tools as gym_tools

def test_conversational_parser():
    text = "bench press 3x8 at 60\nsquat 100kg 5x5 rpe 8"
    sets = gym_service.parse_conversational_sets(text)
    assert len(sets) == 8  # 3 bench + 5 squat
    assert sets[0]["exercise"] == "bench press"
    assert sets[0]["reps"] == 8
    assert sets[0]["weight_kg"] == 60.0

    assert sets[3]["exercise"] == "squat"
    assert sets[3]["reps"] == 5
    assert sets[3]["weight_kg"] == 100.0
    assert sets[3]["rpe"] == 8.0

def test_epley_1rm_and_pr():
    db = SessionLocal()
    try:
        # 60kg x 8 reps -> 1RM = 60 * (1 + 8/30) = 76.0
        one_rm = gym_service.calculate_epley_1rm(60.0, 8)
        assert one_rm == 76.0

        pr1 = gym_service.check_and_update_pr(db, "bench press", 60.0, 8)
        assert pr1["is_pr"] == True
        assert pr1["new_1rm"] == 76.0

        # Higher weight 70kg x 8 reps -> 1RM = 70 * (1 + 8/30) = 88.67 -> new PR
        pr2 = gym_service.check_and_update_pr(db, "bench press", 70.0, 8)
        assert pr2["is_pr"] == True
        assert pr2["old_1rm"] == 76.0
        assert pr2["new_1rm"] > 76.0

        # Lower weight -> no PR
        pr3 = gym_service.check_and_update_pr(db, "bench press", 50.0, 5)
        assert pr3["is_pr"] == False
    finally:
        db.close()

def test_progressive_overload_and_stall():
    db = SessionLocal()
    try:
        # Create 3 workouts with same bench weight (60kg)
        for _ in range(3):
            gym_service.create_workout_with_sets(
                db,
                split_name="Push",
                sets_data=[{"exercise": "bench press", "set_number": 1, "reps": 8, "weight_kg": 60.0}]
            )

        stall = gym_service.check_exercise_stall(db, "bench press")
        assert stall["stalled"] == True
        assert stall["consecutive_sessions"] == 3

        suggestion = gym_service.suggest_progression(db, "bench press")
        assert suggestion["has_history"] == True
        assert suggestion["target"]["reps"] == 9  # +1 rep since reps < 10
    finally:
        db.close()

@pytest.mark.anyio
async def test_gym_tools_end_to_end():
    # Log workout via tool
    res = await gym_tools.handle_log_workout(
        split_name="Legs",
        sets_text="squat 3x10 at 80\nleg press 3x12 at 120"
    )
    assert res["status"] == "success"

    # Get PR for squat
    pr_res = await gym_tools.handle_get_pr("squat")
    assert pr_res["status"] == "success"
    assert pr_res["best_weight_kg"] == 80.0

    # Log Body Weight
    bm_res = await gym_tools.handle_log_body_metric(75.5, 15.0)
    assert bm_res["status"] == "success"

    # Get Gym Stats
    stats_res = await gym_tools.handle_gym_stats()
    assert stats_res["status"] == "success"
    assert len(stats_res["stats"]["prs"]) >= 1
