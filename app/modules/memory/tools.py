from typing import Any, Dict
from sqlalchemy.orm import Session

from app.services import memory as memory_service


def handle_remember_fact(subject: str, predicate: str, value: str, db: Session = None, **kwargs) -> Dict[str, Any]:
    fact = memory_service.remember_fact(db=db, subject=subject, predicate=predicate, value=value)
    return {
        "status": "success",
        "fact_id": fact.id,
        "subject": fact.subject,
        "predicate": fact.predicate,
        "value": fact.value
    }


def handle_recall_fact(query: str, db: Session = None, **kwargs) -> Dict[str, Any]:
    facts = memory_service.recall_facts(db=db, query=query)
    return {
        "count": len(facts),
        "facts": [
            {"subject": f.subject, "predicate": f.predicate, "value": f.value, "created_at": f.created_at.isoformat()}
            for f in facts
        ]
    }


TOOLS: list[Dict[str, Any]] = [
    {
        "type": "function",
        "function": {
            "name": "remember_fact",
            "description": "Stores or updates a structured fact/preference about the owner or world (e.g. subject='owner', predicate='favorite_coffee', value='Espresso').",
            "parameters": {
                "type": "object",
                "properties": {
                    "subject": {"type": "string", "description": "Subject of the fact, e.g. 'owner', 'mom', 'work'"},
                    "predicate": {"type": "string", "description": "Predicate or attribute, e.g. 'favorite_drink', 'birthday'"},
                    "value": {"type": "string", "description": "Value or detail of the fact"}
                },
                "required": ["subject", "predicate", "value"]
            }
        },
        "handler": handle_remember_fact
    },
    {
        "type": "function",
        "function": {
            "name": "recall_fact",
            "description": "Searches stored facts and owner preferences by keyword query.",
            "parameters": {
                "type": "object",
                "properties": {
                    "query": {"type": "string", "description": "Keyword to search for in facts"}
                },
                "required": ["query"]
            }
        },
        "handler": handle_recall_fact
    }
]
