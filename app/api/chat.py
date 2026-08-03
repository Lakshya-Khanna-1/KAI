import uuid
from typing import Optional
from fastapi import APIRouter, Depends, HTTPException, Query, status
from fastapi.responses import StreamingResponse
from pydantic import BaseModel
from sqlalchemy.orm import Session

from app.api.auth import verify_token
from app.db.models.conversation import Conversation
from app.db.models.message import Message
from app.db.session import get_db
from app.llm.loop import stream_agent_loop

router = APIRouter(prefix="/api/chat", tags=["chat"])


class ChatStreamRequest(BaseModel):
    conversation_id: Optional[str] = None
    message: str


@router.post("/stream", dependencies=[Depends(verify_token)])
async def chat_stream_endpoint(
    payload: ChatStreamRequest,
    db: Session = Depends(get_db)
):
    conv_id = payload.conversation_id or str(uuid.uuid4())
    user_text = payload.message.strip()

    if not user_text:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Message cannot be empty")

    generator = stream_agent_loop(conversation_id=conv_id, user_input=user_text, db=db)
    return StreamingResponse(generator, media_type="text/event-stream")


@router.get("/history/{conversation_id}", dependencies=[Depends(verify_token)])
def get_chat_history(
    conversation_id: str,
    db: Session = Depends(get_db)
):
    conv = db.query(Conversation).filter(Conversation.id == conversation_id).first()
    if not conv:
        return {"conversation_id": conversation_id, "messages": []}

    messages = (
        db.query(Message)
        .filter(Message.conversation_id == conversation_id)
        .order_by(Message.created_at.asc())
        .all()
    )
    return {
        "conversation_id": conv.id,
        "title": conv.title,
        "messages": [
            {
                "id": m.id,
                "role": m.role,
                "content": m.content,
                "created_at": m.created_at.isoformat() if m.created_at else None
            }
            for m in messages
        ]
    }
