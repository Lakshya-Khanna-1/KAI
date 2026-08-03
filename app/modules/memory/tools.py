from typing import Any, Dict, List
from app.db.session import SessionLocal
from app.services import memory as memory_service

async def handle_remember(subject: str, predicate: str, value: str) -> Dict[str, Any]:
    db = SessionLocal()
    try:
        fact = memory_service.remember_fact(db, subject, predicate, value)
        return {
            "status": "success",
            "fact": {
                "id": fact.id,
                "subject": fact.subject,
                "predicate": fact.predicate,
                "value": fact.value
            }
        }
    finally:
        db.close()

async def handle_recall(query: str) -> Dict[str, Any]:
    db = SessionLocal()
    try:
        facts = memory_service.recall_facts(db, query)
        return {
            "status": "success",
            "facts": [
                {
                    "id": f.id,
                    "subject": f.subject,
                    "predicate": f.predicate,
                    "value": f.value,
                    "created_at": f.created_at.isoformat() if f.created_at else None
                }
                for f in facts
            ]
        }
    finally:
        db.close()

async def handle_forget(fact_id_or_query: str) -> Dict[str, Any]:
    db = SessionLocal()
    try:
        fact = memory_service.forget_fact(db, fact_id_or_query)
        if fact:
            return {
                "status": "success",
                "message": f"Fact marked as superseded by user request: {fact.subject} {fact.predicate} = {fact.value}",
                "fact_id": fact.id
            }
        return {"status": "error", "message": f"No active fact found matching '{fact_id_or_query}'"}
    finally:
        db.close()

def handle_remember_fact(subject: str, predicate: str, value: str, db=None) -> Dict[str, Any]:
    close_db = False
    if db is None:
        db = SessionLocal()
        close_db = True
    try:
        fact = memory_service.remember_fact(db, subject, predicate, value)
        return {
            "status": "success",
            "fact_id": fact.id,
            "subject": fact.subject,
            "predicate": fact.predicate,
            "value": fact.value
        }
    finally:
        if close_db:
            db.close()

def handle_recall_fact(query: str, db=None) -> Dict[str, Any]:
    close_db = False
    if db is None:
        db = SessionLocal()
        close_db = True
    try:
        facts = memory_service.recall_facts(db, query)
        return {
            "status": "success",
            "count": len(facts),
            "facts": [
                {
                    "id": f.id,
                    "subject": f.subject,
                    "predicate": f.predicate,
                    "value": f.value,
                    "created_at": f.created_at.isoformat() if f.created_at else None
                }
                for f in facts
            ]
        }
    finally:
        if close_db:
            db.close()

TOOLS = [
    {
        "type": "function",
        "function": {
            "name": "remember",
            "description": "Save an atomic fact into permanent memory (subject, predicate, value). Handled automatically or by explicit request.",
            "parameters": {
                "type": "object",
                "properties": {
                    "subject": {"type": "string", "description": "Entity or subject (e.g. 'user', 'kai')"},
                    "predicate": {"type": "string", "description": "Attribute or relation (e.g. 'favorite_food', 'timezone')"},
                    "value": {"type": "string", "description": "The fact value"}
                },
                "required": ["subject", "predicate", "value"]
            }
        },
        "handler": handle_remember
    },
    {
        "type": "function",
        "function": {
            "name": "recall",
            "description": "Recall memories or atomic facts matching a query using hybrid vector and keyword search.",
            "parameters": {
                "type": "object",
                "properties": {
                    "query": {"type": "string", "description": "Search query or topic"}
                },
                "required": ["query"]
            }
        },
        "handler": handle_recall
    },
    {
        "type": "function",
        "function": {
            "name": "forget",
            "description": "Marks a fact as superseded when the user requests to forget or correct it. Never hard deletes.",
            "parameters": {
                "type": "object",
                "properties": {
                    "fact_id_or_query": {"type": "string", "description": "Fact ID or search query identifying the fact to mark superseded"}
                },
                "required": ["fact_id_or_query"]
            }
        },
        "handler": handle_forget
    }
]
