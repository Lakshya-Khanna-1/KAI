import json
import logging
import re
import xml.etree.ElementTree as ET
from datetime import datetime, timezone
from difflib import SequenceMatcher
from typing import Any, Dict, List, Optional
import httpx
from sqlalchemy.orm import Session

from app.db.models.news import NewsItem
from app.db.models.profile import Profile
from app.db.models.roadmap import Roadmap
from app.services import notify

logger = logging.getLogger(__name__)

# Keywords for filtering HN/RSS if not explicitly categorized
AI_KEYWORDS = [
    "ai", "llm", "gpt", "transformer", "neural", "deep learning", "machine learning",
    "qwen", "claude", "gemini", "rag", "agent", "fine-tuning", "diffusion", "vision",
    "embedding", "ollama", "py-torch", "tensorflow", "arxiv"
]


def _normalize_title(title: str) -> str:
    """Normalize title for fuzzy similarity matching."""
    return re.sub(r"[^\w\s]", "", title.lower()).strip()


def _is_duplicate(db: Session, title: str, url: str) -> bool:
    """Check if article exists by exact URL or fuzzy title similarity > 0.85."""
    if db.query(NewsItem).filter(NewsItem.url == url).first():
        return True
    
    norm_t = _normalize_title(title)
    recent_items = db.query(NewsItem).order_by(NewsItem.created_at.desc()).limit(100).all()
    for item in recent_items:
        if SequenceMatcher(None, norm_t, _normalize_title(item.title)).ratio() > 0.85:
            return True
    return False


def extract_user_topics(db: Session) -> List[str]:
    """Gather user interests from profile and active roadmap topics."""
    topics = set()
    
    # 1. Profile interests
    prof = db.query(Profile).first()
    if prof and prof.interests_json:
        try:
            interests = json.loads(prof.interests_json)
            if isinstance(interests, list):
                topics.update([str(i).lower() for i in interests])
        except Exception:
            pass

    # 2. Active roadmap topics
    active_rm = db.query(Roadmap).filter(Roadmap.active == True).first()
    if active_rm:
        for phase in active_rm.phases:
            for top in phase.topics:
                topics.add(top.title.lower())

    if not topics:
        # Default AI topics if user profile/roadmap empty
        topics = {"ai agents", "llm", "deep learning", "python", "system design"}
        
    return list(topics)


def calculate_relevance_score(title: str, summary: str, user_topics: List[str]) -> float:
    """Calculate relevance score (0.0 to 1.0) based on topic match overlap."""
    text = (title + " " + (summary or "")).lower()
    if not user_topics:
        return 0.5

    matched = 0
    for topic in user_topics:
        # Match word boundaries or substring
        if re.search(r"\b" + re.escape(topic) + r"\b", text) or topic in text:
            matched += 1

    # Base score of 0.4 for AI domain items, scaled up to 1.0 for topic matches
    score = 0.4 + min(0.6, (matched / max(1, len(user_topics))) * 2.0)
    return round(min(1.0, score), 2)


def generate_two_line_summary(title: str, raw_text: str) -> str:
    """Clean raw summary to a concise 2-line summary."""
    clean = re.sub(r"\s+", " ", raw_text).strip()
    sentences = re.split(r"(?<=[.!?]) +", clean)
    summary_sentences = [s for s in sentences if len(s) > 10][:2]
    if not summary_sentences:
        return title
    return " ".join(summary_sentences)


async def fetch_arxiv_papers(limit: int = 10) -> List[Dict[str, Any]]:
    """Fetch recent CS papers from arXiv API (cs.AI, cs.CL, cs.LG)."""
    url = f"http://export.arxiv.org/api/query?search_query=cat:cs.AI+OR+cat:cs.CL+OR+cat:cs.LG&sortBy=submittedDate&sortOrder=descending&max_results={limit}"
    results = []
    try:
        async with httpx.AsyncClient(timeout=10.0) as client:
            resp = await client.get(url)
            if resp.status_code == 200:
                root = ET.fromstring(resp.text)
                ns = {"atom": "http://www.w3.org/2005/Atom"}
                for entry in root.findall("atom:entry", ns):
                    title_elem = entry.find("atom:title", ns)
                    summary_elem = entry.find("atom:summary", ns)
                    id_elem = entry.find("atom:id", ns)
                    published_elem = entry.find("atom:published", ns)

                    if title_elem is not None and id_elem is not None:
                        title = title_elem.text.strip().replace("\n", " ")
                        raw_summary = summary_elem.text if summary_elem is not None else title
                        paper_url = id_elem.text.strip()
                        pub_str = published_elem.text.strip() if published_elem is not None else None
                        
                        pub_dt = datetime.now(timezone.utc)
                        if pub_str:
                            try:
                                pub_dt = datetime.fromisoformat(pub_str.replace("Z", "+00:00"))
                            except Exception:
                                pass

                        results.append({
                            "source": "arxiv",
                            "title": title,
                            "url": paper_url,
                            "summary": generate_two_line_summary(title, raw_summary),
                            "published_at": pub_dt
                        })
    except Exception as e:
        logger.error(f"Error fetching arXiv papers: {e}")
    return results


async def fetch_hacker_news_ai(limit: int = 15) -> List[Dict[str, Any]]:
    """Fetch top stories from Hacker News and filter AI/ML related posts."""
    results = []
    try:
        async with httpx.AsyncClient(timeout=10.0) as client:
            top_resp = await client.get("https://hacker-news.firebaseio.com/v0/topstories.json")
            if top_resp.status_code == 200:
                story_ids = top_resp.json()[:30]
                for sid in story_ids:
                    item_resp = await client.get(f"https://hacker-news.firebaseio.com/v0/item/{sid}.json")
                    if item_resp.status_code == 200:
                        item = item_resp.json()
                        if not item or item.get("type") != "story":
                            continue
                        title = item.get("title", "")
                        item_url = item.get("url") or f"https://news.ycombinator.com/item?id={sid}"
                        
                        # Filter for AI/ML keywords
                        if any(kw in title.lower() for kw in AI_KEYWORDS):
                            pub_ts = item.get("time")
                            pub_dt = datetime.fromtimestamp(pub_ts, tz=timezone.utc) if pub_ts else datetime.now(timezone.utc)
                            results.append({
                                "source": "hacker_news",
                                "title": title,
                                "url": item_url,
                                "summary": f"Hacker News top discussion on: {title}",
                                "published_at": pub_dt
                            })
                            if len(results) >= limit:
                                break
    except Exception as e:
        logger.error(f"Error fetching Hacker News AI items: {e}")
    return results


async def fetch_huggingface_papers(limit: int = 10) -> List[Dict[str, Any]]:
    """Fetch trending papers from Hugging Face Daily Papers API."""
    results = []
    try:
        async with httpx.AsyncClient(timeout=10.0) as client:
            resp = await client.get("https://huggingface.co/api/daily_papers")
            if resp.status_code == 200:
                papers = resp.json()[:limit]
                for p in papers:
                    paper_info = p.get("paper", {})
                    title = paper_info.get("title", "")
                    paper_id = paper_info.get("id") or p.get("id")
                    paper_url = f"https://huggingface.co/papers/{paper_id}" if paper_id else "https://huggingface.co/papers"
                    summary_raw = paper_info.get("summary", title)
                    
                    if title:
                        results.append({
                            "source": "huggingface",
                            "title": title,
                            "url": paper_url,
                            "summary": generate_two_line_summary(title, summary_raw),
                            "published_at": datetime.now(timezone.utc)
                        })
    except Exception as e:
        logger.error(f"Error fetching HuggingFace papers: {e}")
    return results


async def fetch_all_news_and_store(db: Session) -> Dict[str, Any]:
    """Fetch from all sources, deduplicate, score relevance, store, and trigger breaking alerts."""
    user_topics = extract_user_topics(db)
    
    arxiv_items = await fetch_arxiv_papers(limit=10)
    hn_items = await fetch_hacker_news_ai(limit=10)
    hf_items = await fetch_huggingface_papers(limit=10)
    
    all_fetched = arxiv_items + hn_items + hf_items
    added_count = 0
    breaking_alerts = 0

    for item in all_fetched:
        if _is_duplicate(db, item["title"], item["url"]):
            continue

        score = calculate_relevance_score(item["title"], item["summary"], user_topics)
        matched_topics = [t for t in user_topics if t in (item["title"] + " " + item["summary"]).lower()]

        news_rec = NewsItem(
            source=item["source"],
            url=item["url"],
            title=item["title"],
            summary=item["summary"],
            published_at=item["published_at"],
            relevance_score=score,
            matched_topics_json=json.dumps(matched_topics),
            seen=False,
            saved=False
        )
        db.add(news_rec)
        db.commit()
        db.refresh(news_rec)
        added_count += 1

        # Trigger breaking alert push if relevance score > 0.85
        if score >= 0.85:
            breaking_alerts += 1
            await notify.send_notification(
                title=f"🚨 High Relevance AI News ({int(score*100)}%)",
                message=f"{news_rec.title}\n{news_rec.summary}",
                priority="high",
                tags=["news", "breaking"],
                click_url=news_rec.url
            )

    return {
        "status": "success",
        "total_fetched": len(all_fetched),
        "new_items_added": added_count,
        "breaking_alerts_sent": breaking_alerts
    }


def get_top_news_digest(db: Session, limit: int = 5) -> List[Dict[str, Any]]:
    """Retrieve top N highest relevance news items for morning briefing digest."""
    items = (
        db.query(NewsItem)
        .order_by(NewsItem.relevance_score.desc(), NewsItem.published_at.desc())
        .limit(limit)
        .all()
    )
    return [
        {
            "id": i.id,
            "source": i.source,
            "title": i.title,
            "summary": i.summary,
            "url": i.url,
            "relevance_score": i.relevance_score
        }
        for i in items
    ]
