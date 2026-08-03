import json
from typing import Any, Dict, List, Optional
from app.db.session import SessionLocal
from app.db.models.roadmap import Roadmap, RoadmapTopic
from app.modules.roadmap import service as roadmap_service

async def handle_preview_roadmap_import(source_text: str) -> Dict[str, Any]:
    db = SessionLocal()
    try:
        parsed_tree = await roadmap_service.parse_roadmap_text(source_text)
        preview_data = roadmap_service.preview_roadmap_import(db, parsed_tree)
        return {
            "status": "success",
            "preview": preview_data
        }
    finally:
        db.close()

async def handle_import_roadmap(source_text: str, confirm: bool = False, roadmap_name: Optional[str] = None) -> Dict[str, Any]:
    db = SessionLocal()
    try:
        parsed_tree = await roadmap_service.parse_roadmap_text(source_text)
        if not confirm:
            preview_data = roadmap_service.preview_roadmap_import(db, parsed_tree)
            return {
                "status": "pending_confirmation",
                "message": "Preview generated. Please confirm before writing to database.",
                "preview": preview_data
            }
        
        name = roadmap_name or parsed_tree.get("name", "Custom Learning Roadmap")
        rm = roadmap_service.commit_roadmap_import(db, name, source_text, parsed_tree)
        return {
            "status": "success",
            "message": f"Successfully imported roadmap '{rm.name}' with ID {rm.id}",
            "roadmap_id": rm.id
        }
    finally:
        db.close()

async def handle_get_roadmap() -> Dict[str, Any]:
    db = SessionLocal()
    try:
        rm = roadmap_service.get_active_roadmap(db)
        if not rm:
            return {"status": "success", "roadmap": None, "message": "No active roadmap found."}
        
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
                        "prerequisites": json.loads(t.prerequisites_json or "[]")
                    }
                    for t in phase.topics
                ]
            })

        return {
            "status": "success",
            "roadmap": {
                "id": rm.id,
                "name": rm.name,
                "active": rm.active,
                "phases": phases_data
            }
        }
    finally:
        db.close()

async def handle_edit_topic(topic_id: str, title: Optional[str] = None, status: Optional[str] = None, est_hours: Optional[float] = None, hours_done: Optional[float] = None) -> Dict[str, Any]:
    db = SessionLocal()
    try:
        topic = db.query(RoadmapTopic).filter(RoadmapTopic.id == topic_id).first()
        if not topic:
            return {"status": "error", "message": f"Topic with ID '{topic_id}' not found."}
        
        if title is not None:
            topic.title = title
        if status is not None:
            topic.status = status
        if est_hours is not None:
            topic.est_hours = est_hours
        if hours_done is not None:
            topic.hours_done = hours_done

        db.commit()
        db.refresh(topic)
        return {
            "status": "success",
            "topic": {
                "id": topic.id,
                "title": topic.title,
                "status": topic.status,
                "est_hours": topic.est_hours,
                "hours_done": topic.hours_done
            }
        }
    finally:
        db.close()

async def handle_archive_roadmap() -> Dict[str, Any]:
    db = SessionLocal()
    try:
        rm = roadmap_service.get_active_roadmap(db)
        if not rm:
            return {"status": "success", "message": "No active roadmap to archive."}
        rm.active = False
        db.commit()
        return {"status": "success", "message": f"Archived roadmap '{rm.name}'"}
    finally:
        db.close()

TOOLS = [
    {
        "type": "function",
        "function": {
            "name": "preview_roadmap_import",
            "description": "Parses raw text of a learning roadmap and returns a proposed structure and diff for confirmation before writing to DB.",
            "parameters": {
                "type": "object",
                "properties": {
                    "source_text": {"type": "string", "description": "Raw markdown or text of the roadmap"}
                },
                "required": ["source_text"]
            }
        },
        "handler": handle_preview_roadmap_import
    },
    {
        "type": "function",
        "function": {
            "name": "import_roadmap",
            "description": "Imports a learning roadmap from raw text. Previews or commits when confirm=True.",
            "parameters": {
                "type": "object",
                "properties": {
                    "source_text": {"type": "string", "description": "Raw text of the roadmap"},
                    "confirm": {"type": "boolean", "description": "Set to true to confirm writing the parsed tree to the database"},
                    "roadmap_name": {"type": "string", "description": "Optional name for the roadmap"}
                },
                "required": ["source_text"]
            }
        },
        "handler": handle_import_roadmap
    },
    {
        "type": "function",
        "function": {
            "name": "get_roadmap",
            "description": "Get the active learning roadmap with all phases, topics, estimated hours, and completion status.",
            "parameters": {"type": "object", "properties": {}},
            "handler": handle_get_roadmap
        },
        "handler": handle_get_roadmap
    },
    {
        "type": "function",
        "function": {
            "name": "edit_topic",
            "description": "Update details or completion status of a roadmap topic.",
            "parameters": {
                "type": "object",
                "properties": {
                    "topic_id": {"type": "string", "description": "ID of the topic"},
                    "title": {"type": "string"},
                    "status": {"type": "string", "enum": ["not_started", "in_progress", "completed"]},
                    "est_hours": {"type": "number"},
                    "hours_done": {"type": "number"}
                },
                "required": ["topic_id"]
            }
        },
        "handler": handle_edit_topic
    },
    {
        "type": "function",
        "function": {
            "name": "archive_roadmap",
            "description": "Archive the currently active learning roadmap (sets active=false, never deletes).",
            "parameters": {"type": "object", "properties": {}},
            "handler": handle_archive_roadmap
        },
        "handler": handle_archive_roadmap
    }
]
