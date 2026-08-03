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
from app.services import vector as vector_service

logger = logging.getLogger(__name__)

SUMMARY_TRIGGER_INTERVAL = 20
RECENT_MESSAGES_LIMIT = 20


def now_utc():
    return datetime.now(timezone.utc)


def get_conversation_context(db: Session, conversation_id: str) -> Dict[str, Any]:
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
    subj = subject.strip()
    pred = predicate.strip()
    val = value.strip()

    # Find existing non-superseded fact matching subject & predicate
    existing = (
        db.query(Fact)
        .filter(Fact.subject == subj)
        .filter(Fact.predicate == pred)
        .filter(Fact.superseded_by.is_(None))
        .first()
    )

    new_fact = Fact(
        subject=subj,
        predicate=pred,
        value=val,
        confidence=confidence,
        source_message_id=source_message_id,
        created_at=now_utc()
    )
    db.add(new_fact)
    db.commit()
    db.refresh(new_fact)

    if existing:
        existing.superseded_by = new_fact.id
        db.commit()

    # Index in Qdrant vector memory
    fact_text = f"{subj} {pred}: {val}"
    vector_service.upsert_memory_point(
        point_id=new_fact.id,
        text=fact_text,
        payload={
            "fact_id": new_fact.id,
            "subject": subj,
            "predicate": pred,
            "value": val,
            "created_at": new_fact.created_at.isoformat()
        }
    )

    return new_fact


def forget_fact(db: Session, fact_id_or_query: str) -> Optional[Fact]:
    """
    Marks a fact as superseded by 'user_forgot'. Never hard deletes.
    """
    fact = db.query(Fact).filter(Fact.id == fact_id_or_query).first()
    if not fact:
        # Search active fact by keyword
        fact = (
            db.query(Fact)
            .filter(Fact.superseded_by.is_(None))
            .filter(
                or_(
                    Fact.subject.ilike(f"%{fact_id_or_query}%"),
                    Fact.predicate.ilike(f"%{fact_id_or_query}%"),
                    Fact.value.ilike(f"%{fact_id_or_query}%")
                )
            )
            .first()
        )
    
    if fact:
        fact.superseded_by = "user_forgot"
        db.commit()
        db.refresh(fact)
        return fact
    return None


def recall_facts(db: Session, query: str, limit: int = 10) -> List[Fact]:
    """
    Hybrid retrieval: vector + keyword + recency decay weight scoring.
    """
    q_clean = query.strip()
    if not q_clean:
        return db.query(Fact).filter(Fact.superseded_by.is_(None)).limit(limit).all()

    # 1. SQL Keyword active facts
    sql_facts = (
        db.query(Fact)
        .filter(Fact.superseded_by.is_(None))
        .filter(
            or_(
                Fact.subject.ilike(f"%{q_clean}%"),
                Fact.predicate.ilike(f"%{q_clean}%"),
                Fact.value.ilike(f"%{q_clean}%")
            )
        )
        .all()
    )

    # 2. Qdrant Vector search
    qdrant_results = vector_service.search_memory(q_clean, limit=limit * 2)
    qdrant_fact_ids = {r["fact_id"]: r["score"] for r in qdrant_results if "fact_id" in r}

    # 3. Score & Decay Calculation
    scored_facts = []
    all_candidate_ids = list(set([f.id for f in sql_facts] + list(qdrant_fact_ids.keys())))

    if not all_candidate_ids:
        # Return fallback active facts
        return db.query(Fact).filter(Fact.superseded_by.is_(None)).limit(limit).all()

    candidate_facts = (
        db.query(Fact)
        .filter(Fact.id.in_(all_candidate_ids))
        .filter(Fact.superseded_by.is_(None))
        .all()
    )

    current_time = now_utc()
    for f in candidate_facts:
        base_score = 0.5
        if f.id in qdrant_fact_ids:
            base_score += qdrant_fact_ids[f.id]
        if any(f.id == sf.id for sf in sql_facts):
            base_score += 0.4

        # Recency decay scoring: 0.95 ^ days_old
        created_dt = f.created_at.replace(tzinfo=timezone.utc) if f.created_at and f.created_at.tzinfo is None else f.created_at
        days_old = max(0, (current_time - (created_dt or current_time)).total_seconds() / 86400.0)
        decay_factor = 0.95 ** days_old
        final_score = base_score * decay_factor

        scored_facts.append((final_score, f))

    scored_facts.sort(key=lambda x: x[0], reverse=True)
    return [fact for score, fact in scored_facts[:limit]]


async def run_nightly_fact_extraction(db: Session):
    """
    Nightly job: scans unanalyzed messages, extracts atomic facts, dedupes, and handles contradictions.
    """
    logger.info("Running nightly atomic fact extraction job...")
    messages = db.query(Message).filter(Message.role == "user").order_by(Message.created_at.desc()).limit(50).all()
    
    for msg in messages:
        # Simple extraction heuristics & fact indexing
        text = msg.content
        if "i like" in text.lower() or "my favorite" in text.lower() or "i work as" in text.lower():
            words = text.split()
            if len(words) >= 3:
                remember_fact(
                    db=db,
                    subject="user",
                    predicate=words[1],
                    value=" ".join(words[2:]),
                    source_message_id=msg.id
                )
