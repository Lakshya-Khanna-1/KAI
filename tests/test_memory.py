import pytest
from app.db.session import SessionLocal
from app.db.models.fact import Fact
from app.services import memory as memory_service
from app.services import vector as vector_service

def test_vector_embedding_and_qdrant():
    emb = vector_service.get_embedding("Test learning python")
    assert isinstance(emb, list)
    assert len(emb) == 768

def test_remember_fact_and_contradiction():
    db = SessionLocal()
    try:
        # Save initial fact
        f1 = memory_service.remember_fact(db, subject="user", predicate="city", value="Delhi")
        assert f1.id is not None
        assert f1.superseded_by is None

        # Save contradicting fact (same subject & predicate)
        f2 = memory_service.remember_fact(db, subject="user", predicate="city", value="Mumbai")
        db.refresh(f1)
        
        assert f2.id is not None
        assert f1.superseded_by == f2.id
    finally:
        db.close()

def test_forget_fact_supersedes():
    db = SessionLocal()
    try:
        f = memory_service.remember_fact(db, subject="user", predicate="hobby", value="Chess")
        forgot = memory_service.forget_fact(db, f.id)
        assert forgot is not None
        assert forgot.superseded_by == "user_forgot"
    finally:
        db.close()

def test_recall_facts_hybrid():
    db = SessionLocal()
    try:
        memory_service.remember_fact(db, subject="user", predicate="favorite_editor", value="Neovim")
        recalled = memory_service.recall_facts(db, "Neovim")
        assert len(recalled) >= 1
        assert any(r.value == "Neovim" for r in recalled)
    finally:
        db.close()
