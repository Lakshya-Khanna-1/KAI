import pytest
from sqlalchemy.orm import Session
from fastapi.testclient import TestClient

from app.main import app
from app.db.models.profile import Profile, OnboardingState
from app.db.models.fact import Fact
from app.modules.onboarding import service
from app.modules.onboarding.tools import (
    handle_get_onboarding_status,
    handle_update_user_profile,
    handle_record_onboarding_question,
    handle_trigger_onboarding,
)
from app.llm.prompt import build_system_prompt

client = TestClient(app)

def test_onboarding_state_initialization(db_session: Session):
    state = service.get_or_create_onboarding_state(db_session)
    assert state.phase == "in_progress"
    assert state.questions_asked == 0
    assert state.completed_at is None

def test_update_profile_key(db_session: Session):
    prof = service.update_profile_key(db_session, key="name", value="Lakshya")
    assert prof.key == "name"
    profile_dict = service.get_profile_dict(db_session)
    assert profile_dict["name"] == "Lakshya"

    # Verify fact entry
    fact = db_session.query(Fact).filter(Fact.predicate == "name").first()
    assert fact is not None
    assert fact.value == "Lakshya"

def test_onboarding_completion_trigger(db_session: Session):
    # Populate all onboarding topics
    for topic in service.ONBOARDING_TOPICS:
        service.update_profile_key(db_session, key=topic, value="test_val")
    
    state = service.get_or_create_onboarding_state(db_session)
    assert state.phase == "completed"
    assert state.completed_at is not None

def test_onboarding_tools(db_session: Session):
    # Status tool
    res_status = handle_get_onboarding_status({}, db_session)
    assert "phase" in res_status
    assert "remaining_topics" in res_status

    # Update profile tool
    res_update = handle_update_user_profile({"key": "communication_style", "value": "concise and direct with dry wit"}, db_session)
    assert res_update["success"] is True
    assert res_update["key"] == "communication_style"

    # Record question tool
    res_rec = handle_record_onboarding_question({}, db_session)
    assert res_rec["success"] is True
    assert res_rec["questions_asked"] == 1

    # Trigger tool
    res_trig = handle_trigger_onboarding({"action": "reset"}, db_session)
    assert res_trig["phase"] == "in_progress"
    assert res_trig["questions_asked"] == 0

def test_onboarding_router_endpoints(db_session: Session):
    # GET /onboarding
    resp = client.get("/onboarding")
    assert resp.status_code == 200
    data = resp.json()
    assert "phase" in data

    # POST /onboarding/profile
    resp_post = client.post("/onboarding/profile", json={"key": "target_role", "value": "AI Engineer"})
    assert resp_post.status_code == 200
    assert resp_post.json()["value"] == "AI Engineer"

    # GET /onboarding/profile
    resp_prof = client.get("/onboarding/profile")
    assert resp_prof.status_code == 200
    assert resp_prof.json()["target_role"] == "AI Engineer"

    # POST /onboarding (reset action)
    resp_trig = client.post("/onboarding", json={"action": "reset"})
    assert resp_trig.status_code == 200
    assert resp_trig.json()["phase"] == "in_progress"

def test_system_prompt_style_adaptation():
    profile = {
        "name": "Lakshya",
        "communication_style": "bullet points, ultra-concise",
        "target_role": "AI Architect"
    }
    prompt = build_system_prompt(
        profile_data=profile,
        onboarding_phase="in_progress",
        unasked_topics=["gym_split", "dietary_notes"]
    )
    assert "Lakshya" in prompt
    assert "bullet points, ultra-concise" in prompt
    assert "Onboarding Interview Active" in prompt
    assert "gym_split" in prompt
