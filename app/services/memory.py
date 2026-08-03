import json
import logging
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional
from sqlalchemy import or_
from sqlalchemy.orm import Session

from app.db.models.conversation import Conversation
from app.db.models.fact import Fact
from app.db.models.message import Message
from app.db.models.summary import ConversationSummary
from app.llm.client import ollama_client

logger = logging.getLogger(__name__)

SUMMARY_TRIGGER_INTERVAL = 20
RECENT_MESSAGES_LIMIT = 20


def get_conversation_context(db: Session, conversation_id: str) -> Dict[str, Any]:
    """
    Returns rolling summary + last 20 messages for prompt context.
    """
    summary_obj = (
        db.query(ConversationSummary)
        .filter(ConversationSummary.conversation_id == conversation_id)
        .first()
    )
    summary_text = summary_obj.summary_text if summary_obj else ""

    messages = (
        db.query(Message)
        .filter(Message.conversation_id == conversation_id)
        .order_by(Message.created_at.asc())
        .all()
    )

    recent_messages = messages[-RECENT_MESSAGES_LIMIT:] if len(messages) > RECENT_MESSAGES_LIMIT else messages

    return {
        "summary": summary_text,
        "recent_messages": [
            {"role": m.role, "content": m.content, "created_at": m.created_at.isoformat() if m.created_at else None}
            for m in recent_messages
        ],
        "total_messages": len(messages)
    }


async def maybe_update_rolling_summary(db: Session, conversation_id: str) -> Optional[str]:
    """
    Checks message count for conversation. If count > 20 and threshold met,
    generates summary of older messages via Ollama and saves to conversation_summaries.
    """
    messages = (
        db.query(Message)
        .filter(Message.conversation_id == conversation_id)
        .order_by(Message.created_at.asc())
        .all()
    )
    total_count = len(messages)
    if total_count <= RECENT_MESSAGES_LIMIT:
        return None

    summary_obj = (
        db.query(ConversationSummary)
        .filter(ConversationSummary.conversation_id == conversation_id)
        .first()
    )

    last_count = summary_obj.message_count_at_summary if summary_obj else 0
    if total_count - last_count < SUMMARY_TRIGGER_INTERVAL:
        return summary_obj.summary_text if summary_obj else None

    # Summarize messages older than the last 20
    older_messages = messages[:-RECENT_MESSAGES_LIMIT]
    older_text = "\n".join([f"{m.role}: {m.content}" for m in older_messages])

    prompt = (
        f"Summarize the following conversation history into a concise memory summary.\n"
        f"Focus on key preferences, facts, and commitments mentioned.\n\n"
        f"CONVERSATION HISTORY:\n{older_text}\n\n"
        f"SUMMARY:"
    )

    try:
        resp = await ollama_client.chat_completion(
            messages=[{"role": "user", "content": prompt}],
            stream=False
        )
        new_summary = resp.get("choices", [{}])[0].get("message", {}).get("content", "").strip()
    except Exception as err:
        logger.error(f"Error generating rolling summary via Ollama: {err}")
        new_summary = f"Conversation summary up to message {total_count - RECENT_MESSAGES_LIMIT}."

    if not summary_obj:
        summary_obj = ConversationSummary(
            conversation_id=conversation_id,
            summary_text=new_summary,
            message_count_at_summary=total_count
        )
        db.add(summary_obj)
    else:
        summary_obj.summary_text = new_summary
        summary_obj.message_count_at_summary = total_count

    db.commit()
    db.refresh(summary_obj)
    return new_summary


def remember_fact(
    db: Session,
    subject: str,
    predicate: str,
    value: str,
    confidence: float = 1.0,
    source_message_id: Optional[str] = None
) -> Fact:
    """
    Stores a new fact or supersedes an existing fact with matching subject & predicate.
    """
    existing = (
        db.query(Fact)
        .filter(Fact.subject == subject.strip())
        .filter(Fact.predicate == predicate.strip())
        .filter(Fact.superseded_by.is_(None))
        .first()
    )

    new_fact = Fact(
        subject=subject.strip(),
        predicate=predicate.strip(),
        value=value.strip(),
        confidence=confidence,
        source_message_id=source_message_id
    )
    db.add(new_fact)
    db.commit()
    db.refresh(new_fact)

    if existing:
        existing.superseded_by = new_fact.id
        db.commit()

    return new_fact


def recall_facts(db: Session, query: str, limit: int = 10) -> List[Fact]:
    """
    Keyword fact retrieval across subject, predicate, and value.
    Returns non-superseded active facts matching query.
    """
    q_str = f"%{query.strip()}%"
    return (
        db.query(Fact)
        .filter(Fact.superseded_by.is_(None))
        .filter(
            or_(
                Fact.subject.ilike(q_str),
                Fact.predicate.ilike(q_str),
                Fact.value.ilike(q_str)
            )
        )
        .limit(limit)
        .all()
    )
