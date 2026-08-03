import json
import logging
import re
from typing import Dict, Any, List, Optional
from sqlalchemy.orm import Session

from app.db.models.roadmap import Roadmap, RoadmapPhase, RoadmapTopic
from app.llm.client import ollama_client
from app.services import vector as vector_service

logger = logging.getLogger(__name__)


def parse_roadmap_heuristic(source_text: str) -> Dict[str, Any]:
    lines = source_text.strip().split("\n")
    phases = []
    roadmap_name = "Custom Learning Roadmap"
    current_phase = {"name": "Phase 1: Overview", "description": "", "topics": []}

    for line in lines:
        raw_line = line.rstrip()
        clean = raw_line.strip()
        if not clean:
            continue

        # Detect H1 title (# Title)
        if clean.startswith("# ") and not clean.startswith("## "):
            roadmap_name = clean.lstrip("#").strip()
            continue

        # Detect Phase/Heading line (##, Phase, Section, Month, Week)
        if clean.startswith("##") or clean.lower().startswith("phase") or clean.lower().startswith("section"):
            if current_phase["topics"]:
                phases.append(current_phase)
            phase_name = clean.lstrip("#").strip()
            current_phase = {"name": phase_name, "description": "", "topics": []}
            continue

        # Detect Topic line (bullet -, *, number, etc.)
        topic_title = re.sub(r"^[-*•\d+\.]+\s*", "", clean)
        
        # Extract URLs
        urls = re.findall(r'https?://[^\s)]+', clean)
        topic_title = re.sub(r'https?://[^\s)]+', '', topic_title).strip()
        
        # Extract hours (e.g. "5 hrs", "3h", "10 hours")
        hours_match = re.search(r'(\d+(?:\.\d+)?)\s*(?:hrs|hours|h)\b', clean, re.IGNORECASE)
        est_hours = float(hours_match.group(1)) if hours_match else 2.0

        current_phase["topics"].append({
            "title": topic_title,
            "est_hours": est_hours,
            "hours_done": 0.0,
            "status": "not_started",
            "prerequisites": [],
            "resources": urls,
            "raw_line": raw_line
        })

    if current_phase["topics"] or not phases:
        phases.append(current_phase)

    return {
        "name": roadmap_name,
        "phases": phases
    }


async def parse_roadmap_text(source_text: str) -> Dict[str, Any]:
    """
    Uses Local LLM to parse arbitrary roadmap text into structured JSON tree.
    Falls back to heuristic parser if LLM call fails.
    """
    prompt = (
        "You are an expert curriculum and roadmap parser. "
        "Parse the following raw text into a structured JSON object representing a learning roadmap.\n"
        "Return ONLY a JSON object with this exact structure:\n"
        "{\n"
        '  "name": "Roadmap Title",\n'
        '  "phases": [\n'
        '    {\n'
        '      "name": "Phase Name",\n'
        '      "description": "Optional phase overview",\n'
        '      "topics": [\n'
        '        {\n'
        '          "title": "Topic Title",\n'
        '          "est_hours": 3.0,\n'
        '          "resources": ["url1", "url2"],\n'
        '          "prerequisites": ["Prereq Topic Title"],\n'
        '          "raw_line": "Original text line"\n'
        '        }\n'
        '      ]\n'
        '    }\n'
        '  ]\n'
        "}\n\n"
        f"RAW ROADMAP TEXT:\n{source_text[:3000]}\n"
    )

    try:
        resp = await ollama_client.chat_completion(
            messages=[{"role": "user", "content": prompt}],
            stream=False
        )
        content = resp.get("choices", [{}])[0].get("message", {}).get("content", "").strip()
        
        # Extract JSON substring
        json_match = re.search(r'\{.*\}', content, re.DOTALL)
        if json_match:
            parsed = json.loads(json_match.group(0))
            if "phases" in parsed and isinstance(parsed["phases"], list):
                return parsed
    except Exception as err:
        logger.warning(f"LLM roadmap parsing failed ({err}). Falling back to heuristic parser.")

    return parse_roadmap_heuristic(source_text)


def preview_roadmap_import(db: Session, parsed_tree: Dict[str, Any]) -> Dict[str, Any]:
    active_roadmap = db.query(Roadmap).filter(Roadmap.active == True).first()

    existing_topics = {}
    if active_roadmap:
        for phase in active_roadmap.phases:
            for top in phase.topics:
                existing_topics[top.title.lower().strip()] = top

    added_topics = []
    retained_topics = []
    total_hours = 0.0

    for phase in parsed_tree.get("phases", []):
        for top in phase.get("topics", []):
            t_title = top.get("title", "").strip()
            total_hours += float(top.get("est_hours", 2.0))
            t_lower = t_title.lower()

            if t_lower in existing_topics:
                existing = existing_topics[t_lower]
                top["hours_done"] = existing.hours_done
                top["status"] = existing.status
                retained_topics.append(t_title)
            else:
                top["hours_done"] = 0.0
                top["status"] = "not_started"
                added_topics.append(t_title)

    new_topic_titles_lower = {top.get("title", "").strip().lower() for p in parsed_tree.get("phases", []) for top in p.get("topics", [])}
    removed_topics = [obj.title for t_lower, obj in existing_topics.items() if t_lower not in new_topic_titles_lower]

    return {
        "roadmap_name": parsed_tree.get("name", "Custom Learning Roadmap"),
        "total_phases": len(parsed_tree.get("phases", [])),
        "total_topics": sum(len(p.get("topics", [])) for p in parsed_tree.get("phases", [])),
        "total_est_hours": total_hours,
        "is_reimport": active_roadmap is not None,
        "active_roadmap_id": active_roadmap.id if active_roadmap else None,
        "diff": {
            "added": added_topics,
            "retained": retained_topics,
            "removed": removed_topics
        },
        "parsed_tree": parsed_tree
    }


def commit_roadmap_import(db: Session, roadmap_name: str, source_text: str, parsed_tree: Dict[str, Any]) -> Roadmap:
    # 1. Archive existing active roadmaps
    db.query(Roadmap).filter(Roadmap.active == True).update({"active": False})
    db.commit()

    # 2. Create new active roadmap
    new_roadmap = Roadmap(
        name=roadmap_name,
        source_text=source_text,
        active=True
    )
    db.add(new_roadmap)
    db.commit()
    db.refresh(new_roadmap)

    # 3. Create phases and topics
    order_p = 0
    for p_data in parsed_tree.get("phases", []):
        phase = RoadmapPhase(
            roadmap_id=new_roadmap.id,
            name=p_data.get("name", f"Phase {order_p + 1}"),
            order_index=order_p,
            description=p_data.get("description", "")
        )
        db.add(phase)
        db.commit()
        db.refresh(phase)
        order_p += 1

        order_t = 0
        for t_data in p_data.get("topics", []):
            topic = RoadmapTopic(
                phase_id=phase.id,
                title=t_data.get("title", "Untitled Topic"),
                est_hours=float(t_data.get("est_hours", 2.0)),
                hours_done=float(t_data.get("hours_done", 0.0)),
                status=t_data.get("status", "not_started"),
                prerequisites_json=json.dumps(t_data.get("prerequisites", [])),
                resources_json=json.dumps(t_data.get("resources", [])),
                order_index=order_t,
                raw_line=t_data.get("raw_line", "")
            )
            db.add(topic)
            db.commit()
            db.refresh(topic)
            order_t += 1

            # Index topic into Qdrant roadmap collection
            vector_service.upsert_memory_point(
                point_id=topic.id,
                text=f"{phase.name} - {topic.title}",
                payload={
                    "topic_id": topic.id,
                    "phase_name": phase.name,
                    "title": topic.title,
                    "est_hours": topic.est_hours,
                    "status": topic.status
                }
            )

    return new_roadmap


def get_active_roadmap(db: Session) -> Optional[Roadmap]:
    return db.query(Roadmap).filter(Roadmap.active == True).first()
