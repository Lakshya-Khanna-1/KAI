from typing import Dict, Any, Optional
from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel
from sqlalchemy.orm import Session

from app.db.session import get_db
from app.db.models.fact import Fact
from app.services import memory as memory_service

router = APIRouter(prefix="/memory", tags=["memory"])

class FactCreateRequest(BaseModel):
    subject: str
    predicate: str
    value: str

class FactUpdateRequest(BaseModel):
    fact_id: str
    subject: str
    predicate: str
    value: str

class ForgetRequest(BaseModel):
    fact_id_or_query: str

class SearchRequest(BaseModel):
    query: str
    limit: Optional[int] = 10

@router.get("")
def list_memory_facts(db: Session = Depends(get_db)):
    facts = db.query(Fact).order_by(Fact.created_at.desc()).all()
    return [
        {
            "id": f.id,
            "subject": f.subject,
            "predicate": f.predicate,
            "value": f.value,
            "confidence": f.confidence,
            "superseded_by": f.superseded_by,
            "created_at": f.created_at.isoformat() if f.created_at else None
        }
        for f in facts
    ]

@router.post("/search")
def search_memory(req: SearchRequest, db: Session = Depends(get_db)):
    facts = memory_service.recall_facts(db, req.query, limit=req.limit or 10)
    return [
        {
            "id": f.id,
            "subject": f.subject,
            "predicate": f.predicate,
            "value": f.value,
            "superseded_by": f.superseded_by,
            "created_at": f.created_at.isoformat() if f.created_at else None
        }
        for f in facts
    ]

@router.post("/remember")
def remember_fact(req: FactCreateRequest, db: Session = Depends(get_db)):
    fact = memory_service.remember_fact(db, req.subject, req.predicate, req.value)
    return {"status": "success", "fact_id": fact.id}

@router.post("/forget")
def forget_fact(req: ForgetRequest, db: Session = Depends(get_db)):
    fact = memory_service.forget_fact(db, req.fact_id_or_query)
    if not fact:
        raise HTTPException(status_code=404, detail="Fact not found")
    return {"status": "success", "fact_id": fact.id, "superseded_by": fact.superseded_by}

@router.post("/update")
def update_fact(req: FactUpdateRequest, db: Session = Depends(get_db)):
    existing = db.query(Fact).filter(Fact.id == req.fact_id).first()
    if not existing:
        raise HTTPException(status_code=404, detail="Fact not found")
    
    # Create new updated fact and set superseded_by on existing
    new_fact = memory_service.remember_fact(db, req.subject, req.predicate, req.value)
    return {"status": "success", "old_fact_id": existing.id, "new_fact_id": new_fact.id}
