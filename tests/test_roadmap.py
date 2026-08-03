import pytest
from app.db.session import SessionLocal
from app.modules.roadmap import service as roadmap_service

SAMPLE_ROADMAP_TEXT = """# Python & AI Mastery Roadmap

## Phase 1: Core Fundamentals
- Python Syntax & Data Structures (4 hours) https://docs.python.org
- Object-Oriented Programming (6 hrs)

## Phase 2: Advanced AI
- PyTorch Basics (10 hours)
- Transformers & LLMs (12 hrs)
"""

ROADMAP_V2_TEXT = """# Python & AI Mastery Roadmap V2

## Phase 1: Core Fundamentals
- Python Syntax & Data Structures (4 hours) https://docs.python.org
- Functional Programming (5 hrs)

## Phase 2: Advanced AI
- Transformers & LLMs (12 hrs)
"""

def test_roadmap_parsing():
    parsed = roadmap_service.parse_roadmap_heuristic(SAMPLE_ROADMAP_TEXT)
    assert parsed["name"] == "Python & AI Mastery Roadmap"
    assert len(parsed["phases"]) == 2
    assert parsed["phases"][0]["topics"][0]["title"] == "Python Syntax & Data Structures (4 hours)"
    assert parsed["phases"][0]["topics"][0]["resources"] == ["https://docs.python.org"]

def test_roadmap_preview_and_commit():
    db = SessionLocal()
    try:
        parsed = roadmap_service.parse_roadmap_heuristic(SAMPLE_ROADMAP_TEXT)
        preview = roadmap_service.preview_roadmap_import(db, parsed)
        assert preview["total_topics"] == 4
        assert preview["total_phases"] == 2

        # Commit roadmap
        rm = roadmap_service.commit_roadmap_import(db, "AI Roadmap", SAMPLE_ROADMAP_TEXT, parsed)
        assert rm.id is not None
        assert rm.active == True

        active = roadmap_service.get_active_roadmap(db)
        assert active.id == rm.id
    finally:
        db.close()

def test_roadmap_reimport_diff():
    db = SessionLocal()
    try:
        # Commit V1
        parsed1 = roadmap_service.parse_roadmap_heuristic(SAMPLE_ROADMAP_TEXT)
        rm1 = roadmap_service.commit_roadmap_import(db, "AI Roadmap V1", SAMPLE_ROADMAP_TEXT, parsed1)

        # Mark topic completed
        first_topic = rm1.phases[0].topics[0]
        first_topic.status = "completed"
        first_topic.hours_done = 4.0
        db.commit()

        # Preview V2 re-import
        parsed2 = roadmap_service.parse_roadmap_heuristic(ROADMAP_V2_TEXT)
        preview2 = roadmap_service.preview_roadmap_import(db, parsed2)
        assert preview2["is_reimport"] == True
        assert len(preview2["diff"]["retained"]) >= 1

        # Commit V2
        rm2 = roadmap_service.commit_roadmap_import(db, "AI Roadmap V2", ROADMAP_V2_TEXT, parsed2)
        db.refresh(rm1)
        assert rm1.active == False
        assert rm2.active == True
    finally:
        db.close()
