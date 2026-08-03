import json
from datetime import datetime, timezone
from typing import Dict, Any, List, Optional
from sqlalchemy.orm import Session

from app.db.models.profile import Profile, OnboardingState
from app.db.models.fact import Fact

ONBOARDING_TOPICS = [
    "name",
    "timezone",
    "wake_sleep_times",
    "work_hours",
    "ai_ml_skill",
    "target_role",
    "weekly_study_hours",
    "gym_split",
    "dietary_notes",
    "communication_style",
    "motivation",
    "annoyances",
    "learning_roadmap"
]

def now_utc():
    return datetime.now(timezone.utc)

def get_or_create_onboarding_state(db: Session) -> OnboardingState:
    state = db.query(OnboardingState).first()
    if not state:
        state = OnboardingState(phase="in_progress", questions_asked=0)
        db.add(state)
        db.commit()
        db.refresh(state)
    return state

def get_profile_dict(db: Session) -> Dict[str, Any]:
    rows = db.query(Profile).all()
    result = {}
    for r in rows:
        if r.value_json:
            try:
                result[r.key] = json.loads(r.value_json)
            except Exception:
                result[r.key] = r.value_json
    return result

def update_profile_key(db: Session, key: str, value: Any, message_id: Optional[str] = None) -> Profile:
    val_json = json.dumps(value) if not isinstance(value, str) else json.dumps(value)
    
    prof = db.query(Profile).filter(Profile.key == key).first()
    if not prof:
        prof = Profile(key=key, value_json=val_json, updated_at=now_utc())
        db.add(prof)
    else:
        prof.value_json = val_json
        prof.updated_at = now_utc()
    
    # Also write to facts table for unstructured memory
    fact = Fact(
        subject="user",
        predicate=key,
        value=str(value),
        confidence=1.0,
        source_message_id=message_id,
        created_at=now_utc()
    )
    db.add(fact)
    db.commit()
    db.refresh(prof)

    # Check if all onboarding topics are filled
    current_profile = get_profile_dict(db)
    if all(topic in current_profile for topic in ONBOARDING_TOPICS):
        state = get_or_create_onboarding_state(db)
        if state.phase != "completed":
            state.phase = "completed"
            state.completed_at = now_utc()
            db.commit()

    return prof

def get_unasked_topics(db: Session) -> List[str]:
    prof = get_profile_dict(db)
    return [t for t in ONBOARDING_TOPICS if t not in prof]

def record_question_asked(db: Session) -> OnboardingState:
    state = get_or_create_onboarding_state(db)
    state.questions_asked += 1
    db.commit()
    db.refresh(state)
    return state

def reset_onboarding(db: Session) -> OnboardingState:
    state = get_or_create_onboarding_state(db)
    state.phase = "in_progress"
    state.questions_asked = 0
    state.completed_at = None
    db.commit()
    db.refresh(state)
    return state

def skip_onboarding(db: Session) -> OnboardingState:
    state = get_or_create_onboarding_state(db)
    state.phase = "skipped"
    state.completed_at = now_utc()
    db.commit()
    db.refresh(state)
    return state

def complete_onboarding(db: Session) -> OnboardingState:
    state = get_or_create_onboarding_state(db)
    state.phase = "completed"
    state.completed_at = now_utc()
    db.commit()
    db.refresh(state)
    return state
