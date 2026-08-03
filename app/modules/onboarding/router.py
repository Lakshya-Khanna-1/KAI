from typing import Dict, Any
from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.orm import Session

from app.db.session import get_db
from app.modules.onboarding import service
from app.modules.onboarding.models import OnboardingStatus, UpdateProfilePayload, OnboardingTriggerPayload

router = APIRouter(prefix="/onboarding", tags=["onboarding"])

@router.get("", response_model=OnboardingStatus)
def get_onboarding_status(db: Session = Depends(get_db)):
    state = service.get_or_create_onboarding_state(db)
    profile = service.get_profile_dict(db)
    unasked = service.get_unasked_topics(db)
    return OnboardingStatus(
        phase=state.phase,
        questions_asked=state.questions_asked,
        completed_at=state.completed_at,
        profile=profile
    )

@router.post("", response_model=OnboardingStatus)
def trigger_onboarding(payload: OnboardingTriggerPayload, db: Session = Depends(get_db)):
    action = payload.action.lower()
    if action == "reset":
        service.reset_onboarding(db)
    elif action == "skip":
        service.skip_onboarding(db)
    elif action == "complete":
        service.complete_onboarding(db)
    else:
        service.get_or_create_onboarding_state(db)
        
    state = service.get_or_create_onboarding_state(db)
    profile = service.get_profile_dict(db)
    return OnboardingStatus(
        phase=state.phase,
        questions_asked=state.questions_asked,
        completed_at=state.completed_at,
        profile=profile
    )

@router.get("/profile")
def get_profile(db: Session = Depends(get_db)):
    return service.get_profile_dict(db)

@router.post("/profile")
def update_profile(payload: UpdateProfilePayload, db: Session = Depends(get_db)):
    prof = service.update_profile_key(db, key=payload.key, value=payload.value)
    return {"key": prof.key, "value": payload.value}
