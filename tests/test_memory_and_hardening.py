import os
import shutil
import tempfile
import pytest
from sqlalchemy.orm import Session

from app.db.models.conversation import Conversation
from app.db.models.fact import Fact
from app.db.models.message import Message
from app.db.models.summary import ConversationSummary
from app.modules.memory.tools import handle_recall_fact, handle_remember_fact
from app.services import memory as memory_service
from app.services.backup import perform_db_backup


def test_fact_remember_and_recall(db_session: Session):
    # Remember fact 1
    res1 = handle_remember_fact(
        subject="owner",
        predicate="favorite_coffee",
        value="Double Espresso",
        db=db_session
    )
    assert res1["status"] == "success"
    assert res1["value"] == "Double Espresso"

    # Recall fact
    res_search = handle_recall_fact(query="coffee", db=db_session)
    assert res_search["count"] == 1
    assert res_search["facts"][0]["value"] == "Double Espresso"

    # Supersede fact with new value
    res2 = handle_remember_fact(
        subject="owner",
        predicate="favorite_coffee",
        value="Oat Milk Flat White",
        db=db_session
    )
    assert res2["status"] == "success"

    # Search coffee again -> should return only new active non-superseded fact
    res_search_updated = handle_recall_fact(query="coffee", db=db_session)
    assert res_search_updated["count"] == 1
    assert res_search_updated["facts"][0]["value"] == "Oat Milk Flat White"


def test_conversation_context_window(db_session: Session):
    conv_id = "test-conv-window"
    conv = Conversation(id=conv_id, title="Window Test")
    db_session.add(conv)
    db_session.commit()

    # Add 25 messages
    for i in range(1, 26):
        msg = Message(
            conversation_id=conv_id,
            role="user" if i % 2 != 0 else "assistant",
            content=f"Message number {i}"
        )
        db_session.add(msg)
    db_session.commit()

    ctx = memory_service.get_conversation_context(db=db_session, conversation_id=conv_id)
    assert ctx["total_messages"] == 25
    # Recent messages should be capped at 20 (last 20 messages: 6..25)
    assert len(ctx["recent_messages"]) == 20
    assert ctx["recent_messages"][0]["content"] == "Message number 6"
    assert ctx["recent_messages"][-1]["content"] == "Message number 25"


def test_db_backup_service(db_session: Session, tmp_path):
    with pytest.MonkeyPatch.context() as m:
        m.setattr("app.services.backup.BACKUP_DIR", tmp_path)
        backup_path = perform_db_backup()
        assert backup_path != ""
        assert os.path.exists(backup_path)
        assert "kai_backup_" in backup_path
