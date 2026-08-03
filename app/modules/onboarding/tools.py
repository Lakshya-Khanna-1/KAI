from typing import Dict, Any, List, Optional
from sqlalchemy.orm import Session

from app.modules.onboarding import service

def handle_get_onboarding_status(args: Dict[str, Any], db: Session) -> Dict[str, Any]:
    state = service.get_or_create_onboarding_state(db)
    profile = service.get_profile_dict(db)
    unasked = service.get_unasked_topics(db)
    return {
        "phase": state.phase,
        "questions_asked": state.questions_asked,
        "completed_at": state.completed_at.isoformat() if state.completed_at else None,
        "remaining_topics": unasked,
        "profile": profile
    }

def handle_update_user_profile(args: Dict[str, Any], db: Session) -> Dict[str, Any]:
    key = args.get("key")
    value = args.get("value")
    if not key or value is None:
        return {"error": "Both 'key' and 'value' are required."}
    
    prof = service.update_profile_key(db, key=key, value=value)
    state = service.get_or_create_onboarding_state(db)
    remaining = service.get_unasked_topics(db)
    
    return {
        "success": True,
        "key": prof.key,
        "value": value,
        "remaining_topics": remaining,
        "onboarding_phase": state.phase
    }

def handle_record_onboarding_question(args: Dict[str, Any], db: Session) -> Dict[str, Any]:
    state = service.record_question_asked(db)
    return {
        "success": True,
        "questions_asked": state.questions_asked,
        "phase": state.phase
    }

def handle_trigger_onboarding(args: Dict[str, Any], db: Session) -> Dict[str, Any]:
    action = args.get("action", "resume")
    if action == "reset":
        state = service.reset_onboarding(db)
    elif action == "skip":
        state = service.skip_onboarding(db)
    elif action == "complete":
        state = service.complete_onboarding(db)
    else:
        state = service.get_or_create_onboarding_state(db)
        
    profile = service.get_profile_dict(db)
    remaining = service.get_unasked_topics(db)
    
    return {
        "action": action,
        "phase": state.phase,
        "questions_asked": state.questions_asked,
        "remaining_topics": remaining,
        "profile": profile
    }

TOOLS = [
    {
        "type": "function",
        "function": {
            "name": "get_onboarding_status",
            "description": "Check current onboarding state, questions asked count, remaining profile topics, and stored profile details.",
            "parameters": {
                "type": "object",
                "properties": {},
                "required": []
            }
        },
        "handler": handle_get_onboarding_status
    },
    {
        "type": "function",
        "function": {
            "name": "update_user_profile",
            "description": "Save or update structured user profile attributes (name, timezone, wake_sleep_times, work_hours, ai_ml_skill, target_role, weekly_study_hours, gym_split, dietary_notes, communication_style, motivation, annoyances).",
            "parameters": {
                "type": "object",
                "properties": {
                    "key": {
                        "type": "string",
                        "description": "Profile key to save (e.g. name, timezone, wake_sleep_times, work_hours, ai_ml_skill, target_role, weekly_study_hours, gym_split, dietary_notes, communication_style, motivation, annoyances)"
                    },
                    "value": {
                        "type": "string",
                        "description": "The user's answer/preference for this attribute"
                    }
                },
                "required": ["key", "value"]
            }
        },
        "handler": handle_update_user_profile
    },
    {
        "type": "function",
        "function": {
            "name": "record_onboarding_question",
            "description": "Record that an onboarding interview question was asked in the current session (max 4 per session).",
            "parameters": {
                "type": "object",
                "properties": {},
                "required": []
            }
        },
        "handler": handle_record_onboarding_question
    },
    {
        "type": "function",
        "function": {
            "name": "trigger_onboarding",
            "description": "Trigger, resume, skip, or reset the onboarding interview session.",
            "parameters": {
                "type": "object",
                "properties": {
                    "action": {
                        "type": "string",
                        "description": "Action to take: 'start', 'resume', 'skip', 'reset', or 'complete'",
                        "enum": ["start", "resume", "skip", "reset", "complete"]
                    }
                },
                "required": ["action"]
            }
        },
        "handler": handle_trigger_onboarding
    }
]
