import json
from typing import Any, Dict, List, Optional
from app.db.session import SessionLocal
from app.db.models.news import NewsItem
from app.modules.news import service as news_service
from app.llm import client as llm_client

async def handle_get_news(saved_only: bool = False, source: Optional[str] = None, limit: int = 10) -> Dict[str, Any]:
    db = SessionLocal()
    try:
        query = db.query(NewsItem)
        if saved_only:
            query = query.filter(NewsItem.saved == True)
        if source:
            query = query.filter(NewsItem.source == source)
        
        items = query.order_by(NewsItem.relevance_score.desc(), NewsItem.published_at.desc()).limit(limit).all()
        return {
            "status": "success",
            "count": len(items),
            "news": [
                {
                    "id": item.id,
                    "source": item.source,
                    "title": item.title,
                    "summary": item.summary,
                    "url": item.url,
                    "relevance_score": item.relevance_score,
                    "saved": item.saved,
                    "published_at": item.published_at.strftime("%Y-%m-%d %H:%M")
                }
                for item in items
            ]
        }
    finally:
        db.close()

async def handle_save_article(news_id: Optional[str] = None, url: Optional[str] = None, save: bool = True) -> Dict[str, Any]:
    db = SessionLocal()
    try:
        item = None
        if news_id:
            item = db.query(NewsItem).filter(NewsItem.id == news_id).first()
        elif url:
            item = db.query(NewsItem).filter(NewsItem.url == url).first()

        if not item:
            return {"status": "error", "message": "News item not found."}

        item.saved = save
        db.commit()
        db.refresh(item)
        action = "saved for later study" if save else "unsaved"
        return {"status": "success", "message": f"Article '{item.title}' {action}.", "saved": item.saved}
    finally:
        db.close()

async def handle_explain_paper(news_id: Optional[str] = None, query: Optional[str] = None) -> Dict[str, Any]:
    db = SessionLocal()
    try:
        item = None
        if news_id:
            item = db.query(NewsItem).filter(NewsItem.id == news_id).first()
        elif query:
            item = db.query(NewsItem).filter(NewsItem.title.ilike(f"%{query}%")).first()

        if not item and not query:
            return {"status": "error", "message": "Please provide a valid news item ID or topic query to explain."}

        title = item.title if item else query
        summary = item.summary if item else ""
        url = item.url if item else ""

        try:
            prompt = (
                f"Explain this research paper / AI article in plain language, detailing why it matters, "
                f"key technical takeaways, and practical applications:\n\nTitle: {title}\nSummary: {summary}\nURL: {url}"
            )

            resp = await ollama_client.chat_completion(
                messages=[
                    {"role": "system", "content": "You are a senior AI research scientist explaining technical papers clearly and concisely."},
                    {"role": "user", "content": prompt}
                ],
                stream=False
            )

            choices = resp.get("choices", [])
            explanation = choices[0]["message"]["content"] if choices else summary
        except Exception as err:
            explanation = f"{summary}\n\n[Note: Local model detailed breakdown unavailable: {err}]"

        return {
            "status": "success",
            "title": title,
            "url": url,
            "explanation": explanation
        }
    finally:
        db.close()

async def handle_search_news(query: str, limit: int = 10) -> Dict[str, Any]:
    db = SessionLocal()
    try:
        items = db.query(NewsItem).filter(
            (NewsItem.title.ilike(f"%{query}%")) | (NewsItem.summary.ilike(f"%{query}%"))
        ).order_by(NewsItem.relevance_score.desc()).limit(limit).all()

        return {
            "status": "success",
            "query": query,
            "count": len(items),
            "results": [
                {
                    "id": item.id,
                    "source": item.source,
                    "title": item.title,
                    "summary": item.summary,
                    "url": item.url,
                    "relevance_score": item.relevance_score,
                    "saved": item.saved
                }
                for item in items
            ]
        }
    finally:
        db.close()

TOOLS = [
    {
        "type": "function",
        "function": {
            "name": "get_news",
            "description": "Fetch recent AI research papers and news articles filtered by source or saved status.",
            "parameters": {
                "type": "object",
                "properties": {
                    "saved_only": {"type": "boolean", "description": "If true, returns only articles saved for later study"},
                    "source": {"type": "string", "description": "Filter source: arxiv, hacker_news, huggingface"},
                    "limit": {"type": "integer", "description": "Number of articles (default 10)"}
                }
            }
        },
        "handler": handle_get_news
    },
    {
        "type": "function",
        "function": {
            "name": "save_article",
            "description": "Save an article or paper for later study or remove it from saved.",
            "parameters": {
                "type": "object",
                "properties": {
                    "news_id": {"type": "string", "description": "ID of the news item"},
                    "url": {"type": "string", "description": "URL of the news item if ID not available"},
                    "save": {"type": "boolean", "description": "True to save, False to unsave (default True)"}
                }
            }
        },
        "handler": handle_save_article
    },
    {
        "type": "function",
        "function": {
            "name": "explain_paper",
            "description": "Provide a deep plain-language breakdown of an AI research paper or news article.",
            "parameters": {
                "type": "object",
                "properties": {
                    "news_id": {"type": "string", "description": "ID of news item to explain"},
                    "query": {"type": "string", "description": "Title or topic query to search and explain"}
                }
            }
        },
        "handler": handle_explain_paper
    },
    {
        "type": "function",
        "function": {
            "name": "search_news",
            "description": "Search stored news items and papers by keyword.",
            "parameters": {
                "type": "object",
                "properties": {
                    "query": {"type": "string", "description": "Search keyword or topic"},
                    "limit": {"type": "integer", "description": "Max results (default 10)"}
                },
                "required": ["query"]
            }
        },
        "handler": handle_search_news
    }
]
