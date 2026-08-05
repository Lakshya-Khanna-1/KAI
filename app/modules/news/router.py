from typing import Optional
from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.orm import Session
from pydantic import BaseModel

from app.db.session import get_db
from app.db.models.news import NewsItem
from app.modules.news import service as news_service
from app.modules.news import tools as news_tools

router = APIRouter(prefix="/news", tags=["news"])

class SaveRequest(BaseModel):
    saved: bool = True

@router.get("")
def list_news(
    saved: Optional[bool] = None,
    source: Optional[str] = None,
    limit: int = 20,
    db: Session = Depends(get_db)
):
    query = db.query(NewsItem)
    if saved is not None:
        query = query.filter(NewsItem.saved == saved)
    if source:
        query = query.filter(NewsItem.source == source)

    items = query.order_by(NewsItem.relevance_score.desc(), NewsItem.published_at.desc()).limit(limit).all()
    return {
        "status": "success",
        "count": len(items),
        "items": [
            {
                "id": i.id,
                "source": i.source,
                "title": i.title,
                "summary": i.summary,
                "url": i.url,
                "relevance_score": i.relevance_score,
                "saved": i.saved,
                "seen": i.seen,
                "published_at": i.published_at.strftime("%Y-%m-%d %H:%M")
            }
            for i in items
        ]
    }

@router.post("/fetch")
async def trigger_fetch(db: Session = Depends(get_db)):
    res = await news_service.fetch_all_news_and_store(db)
    return res

@router.post("/{item_id}/save")
def toggle_save(item_id: str, req: SaveRequest, db: Session = Depends(get_db)):
    item = db.query(NewsItem).filter(NewsItem.id == item_id).first()
    if not item:
        raise HTTPException(status_code=404, detail="News item not found")
    item.saved = req.saved
    db.commit()
    return {"status": "success", "id": item.id, "saved": item.saved}

@router.post("/{item_id}/explain")
async def explain_news_item(item_id: str):
    res = await news_tools.handle_explain_paper(news_id=item_id)
    return res
