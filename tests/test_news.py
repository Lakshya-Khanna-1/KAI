import asyncio
import pytest
from fastapi.testclient import TestClient

from app.main import app
from app.db.models.news import NewsItem
from app.modules.news import service as news_service
from app.modules.news import tools as news_tools

client = TestClient(app)

@pytest.fixture
def clean_news(db_session):
    db_session.query(NewsItem).delete()
    db_session.commit()

def test_calculate_relevance_score():
    topics = ["ai agents", "qwen", "transformer"]
    score1 = news_service.calculate_relevance_score("Building AI Agents with Qwen", "Deep dive into agents", topics)
    assert score1 > 0.6
    
    score2 = news_service.calculate_relevance_score("Unrelated Cooking Recipe", "Baking bread at home", topics)
    assert score2 == 0.4

def test_deduplication_check(db_session, clean_news):
    item1 = NewsItem(
        source="arxiv",
        url="https://arxiv.org/abs/2401.00001",
        title="Attention Is All You Need V2",
        summary="A new transformer model architecture.",
        relevance_score=0.9
    )
    db_session.add(item1)
    db_session.commit()

    # Exact URL duplicate
    assert news_service._is_duplicate(db_session, "Different Title", "https://arxiv.org/abs/2401.00001") == True
    # Fuzzy title duplicate
    assert news_service._is_duplicate(db_session, "Attention is all you need v2!", "https://arxiv.org/abs/2401.00002") == True
    # New unique item
    assert news_service._is_duplicate(db_session, "Diffusion Models in Robotics", "https://arxiv.org/abs/2401.00003") == False

def test_news_tools_get_and_save(db_session, clean_news):
    item = NewsItem(
        source="hacker_news",
        url="https://news.ycombinator.com/item?id=12345",
        title="Show HN: Local AI Assistant",
        summary="Self hosted assistant for daily productivity.",
        relevance_score=0.85,
        saved=False
    )
    db_session.add(item)
    db_session.commit()

    # Test get_news
    res_get = asyncio.run(news_tools.handle_get_news(limit=5))
    assert res_get["status"] == "success"
    assert res_get["count"] >= 1
    assert res_get["news"][0]["title"] == "Show HN: Local AI Assistant"

    # Test save_article
    res_save = asyncio.run(news_tools.handle_save_article(news_id=item.id, save=True))
    assert res_save["status"] == "success"
    assert res_save["saved"] == True

    # Check get_news with saved_only=True
    res_saved_only = asyncio.run(news_tools.handle_get_news(saved_only=True))
    assert res_saved_only["count"] == 1

def test_search_news_tool(db_session, clean_news):
    item = NewsItem(
        source="huggingface",
        url="https://huggingface.co/papers/2401.9999",
        title="Llama 3 Fine-tuning Guide",
        summary="Optimizing open models for edge inference.",
        relevance_score=0.88
    )
    db_session.add(item)
    db_session.commit()

    res_search = asyncio.run(news_tools.handle_search_news(query="Llama"))
    assert res_search["status"] == "success"
    assert res_search["count"] == 1
    assert res_search["results"][0]["source"] == "huggingface"

def test_news_router_endpoints(db_session, clean_news):
    from app.config import settings
    auth_headers = {"Authorization": f"Bearer {settings.API_TOKEN}"} if settings.API_TOKEN else {}

    item = NewsItem(
        source="arxiv",
        url="https://arxiv.org/abs/2401.7777",
        title="Agentic Workflows in LLMs",
        summary="Analyzing multi-agent performance.",
        relevance_score=0.92
    )
    db_session.add(item)
    db_session.commit()

    # GET /news
    resp = client.get("/news", headers=auth_headers)
    assert resp.status_code == 200
    data = resp.json()
    assert data["status"] == "success"
    assert len(data["items"]) >= 1

    # POST /news/{id}/save
    resp_save = client.post(f"/news/{item.id}/save", json={"saved": True}, headers=auth_headers)
    assert resp_save.status_code == 200
    assert resp_save.json()["saved"] == True
