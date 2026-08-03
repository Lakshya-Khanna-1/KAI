import json
import logging
from typing import Dict, Any, Optional
from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
from sqlalchemy.orm import Session

from app.db.session import get_db
from app.db.models.roadmap import RoadmapTopic
from app.modules.roadmap import service as roadmap_service

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/roadmap", tags=["roadmap"])

class PreviewRequest(BaseModel):
    source_text: str

class ImportRequest(BaseModel):
    source_text: str
    roadmap_name: Optional[str] = None
    confirm: bool = False

class TopicUpdateRequest(BaseModel):
    topic_id: str
    title: Optional[str] = None
    status: Optional[str] = None
    est_hours: Optional[float] = None
    hours_done: Optional[float] = None

@router.post("/preview")
async def preview_roadmap(req: PreviewRequest, db: Session = Depends(get_db)):
    parsed_tree = await roadmap_service.parse_roadmap_text(req.source_text)
    preview_data = roadmap_service.preview_roadmap_import(db, parsed_tree)
    return {"status": "success", "preview": preview_data}

@router.post("/import")
async def import_roadmap(req: ImportRequest, db: Session = Depends(get_db)):
    parsed_tree = await roadmap_service.parse_roadmap_text(req.source_text)
    if not req.confirm:
        preview_data = roadmap_service.preview_roadmap_import(db, parsed_tree)
        return {
            "status": "pending_confirmation",
            "message": "Preview generated. Confirm to save.",
            "preview": preview_data
        }
    
    name = req.roadmap_name or parsed_tree.get("name", "Custom Learning Roadmap")
    rm = roadmap_service.commit_roadmap_import(db, name, req.source_text, parsed_tree)
    return {"status": "success", "roadmap_id": rm.id, "name": rm.name}

@router.get("/active")
def get_active_roadmap(db: Session = Depends(get_db)):
    rm = roadmap_service.get_active_roadmap(db)
    if not rm:
        return {"roadmap": None}
    
    phases_data = []
    for phase in rm.phases:
        phases_data.append({
            "id": phase.id,
            "name": phase.name,
            "order_index": phase.order_index,
            "topics": [
                {
                    "id": t.id,
                    "title": t.title,
                    "est_hours": t.est_hours,
                    "hours_done": t.hours_done,
                    "status": t.status,
                    "resources": json.loads(t.resources_json or "[]"),
                    "prerequisites": json.loads(t.prerequisites_json or "[]"),
                    "raw_line": t.raw_line
                }
                for t in phase.topics
            ]
        })

    return {
        "roadmap": {
            "id": rm.id,
            "name": rm.name,
            "active": rm.active,
            "created_at": rm.created_at.isoformat() if rm.created_at else None,
            "phases": phases_data
        }
    }

@router.post("/topic/update")
def update_topic(req: TopicUpdateRequest, db: Session = Depends(get_db)):
    topic = db.query(RoadmapTopic).filter(RoadmapTopic.id == req.topic_id).first()
    if not topic:
        raise HTTPException(status_code=404, detail="Topic not found")
    
    if req.title is not None:
        topic.title = req.title
    if req.status is not None:
        topic.status = req.status
    if req.est_hours is not None:
        topic.est_hours = req.est_hours
    if req.hours_done is not None:
        topic.hours_done = req.hours_done

    db.commit()
    db.refresh(topic)
    return {"status": "success", "topic_id": topic.id}

@router.post("/archive")
def archive_roadmap(db: Session = Depends(get_db)):
    rm = roadmap_service.get_active_roadmap(db)
    if rm:
        rm.active = False
        db.commit()
    return {"status": "success"}
