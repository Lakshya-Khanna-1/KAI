import uuid
from datetime import datetime, timezone
from sqlalchemy import Column, String, Float, Boolean, DateTime, Text
from app.db.base import Base

class NewsItem(Base):
    __tablename__ = "news_items"

    id = Column(String, primary_key=True, default=lambda: str(uuid.uuid4()))
    source = Column(String, nullable=False, index=True)  # arxiv, hacker_news, huggingface, rss
    url = Column(String, unique=True, nullable=False, index=True)
    title = Column(String, nullable=False)
    summary = Column(Text, nullable=True)
    published_at = Column(DateTime, nullable=False, default=lambda: datetime.now(timezone.utc))
    relevance_score = Column(Float, default=0.0, index=True)
    matched_topics_json = Column(Text, default="[]")
    seen = Column(Boolean, default=False)
    saved = Column(Boolean, default=False, index=True)
    created_at = Column(DateTime, default=lambda: datetime.now(timezone.utc))
