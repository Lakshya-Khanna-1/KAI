import asyncio
import uuid
import pytest
from unittest.mock import AsyncMock, patch
from sqlalchemy.orm import Session

from app.db.models.conversation import Conversation
from app.db.models.message import Message
from app.db.models.tool_call import ToolCall
from app.llm.loop import parse_tool_calls_from_response, run_agent_loop
from app.llm.prompt import build_system_prompt
from app.llm.registry import tool_registry


def test_build_system_prompt():
    prompt = build_system_prompt(owner_name="Alice", tz_name="UTC")
    assert "Alice" in prompt
    assert "Current Time:" in prompt
    assert "UTC" in prompt
    assert "Tool Usage Instructions:" in prompt


def test_tool_registry_discovery():
    tool_registry.reload()
    schemas = tool_registry.get_schemas()
    names = [s["function"]["name"] for s in schemas]
    assert "get_current_time" in names
    assert tool_registry.get_handler("get_current_time") is not None


def test_parse_native_tool_calls():
    native_msg = {
        "role": "assistant",
        "tool_calls": [
            {
                "id": "call_123",
                "function": {
                    "name": "get_current_time",
                    "arguments": '{"timezone": "Asia/Kolkata"}'
                }
            }
        ]
    }
    calls, ok, err = parse_tool_calls_from_response(native_msg)
    assert ok is True
    assert err is None
    assert len(calls) == 1
    assert calls[0]["name"] == "get_current_time"
    assert calls[0]["arguments"] == {"timezone": "Asia/Kolkata"}


def test_parse_json_text_tool_calls():
    text_msg = {
        "role": "assistant",
        "content": 'Here is the tool call:\n```json\n{"name": "get_current_time", "arguments": {}}\n```'
    }
    calls, ok, err = parse_tool_calls_from_response(text_msg)
    assert ok is True
    assert err is None
    assert len(calls) == 1
    assert calls[0]["name"] == "get_current_time"


def test_agent_loop_end_to_end_mocked(db_session: Session):
    conv_id = str(uuid.uuid4())
    
    mock_llm = AsyncMock()
    # First response requests tool call get_current_time
    mock_llm.chat_completion.side_effect = [
        {
            "choices": [
                {
                    "message": {
                        "role": "assistant",
                        "content": None,
                        "tool_calls": [
                            {
                                "id": "call_test_01",
                                "function": {
                                    "name": "get_current_time",
                                    "arguments": '{"timezone": "Asia/Kolkata"}'
                                }
                            }
                        ]
                    }
                }
            ]
        },
        # Second response returns final text
        {
            "choices": [
                {
                    "message": {
                        "role": "assistant",
                        "content": "The current time in Asia/Kolkata is 05:30 PM."
                    }
                }
            ]
        }
    ]

    response = asyncio.run(
        run_agent_loop(
            conversation_id=conv_id,
            user_input="What time is it?",
            db=db_session,
            client=mock_llm
        )
    )

    assert response == "The current time in Asia/Kolkata is 05:30 PM."

    # Verify conversation & messages created
    conv = db_session.query(Conversation).filter(Conversation.id == conv_id).first()
    assert conv is not None

    messages = db_session.query(Message).filter(Message.conversation_id == conv_id).all()
    assert len(messages) >= 2

    # Verify tool_calls DB table logged the execution!
    logged_tool_calls = db_session.query(ToolCall).all()
    assert len(logged_tool_calls) >= 1
    call_record = logged_tool_calls[-1]
    assert call_record.tool_name == "get_current_time"
    assert call_record.ok is True
    assert "Asia/Kolkata" in call_record.args_json
    assert call_record.duration_ms is not None
