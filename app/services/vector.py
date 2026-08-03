import hashlib
import logging
import uuid
from typing import Dict, Any, List, Optional
import httpx
from qdrant_client import QdrantClient
from qdrant_client.http import models as qmodels

from app.config import settings

logger = logging.getLogger(__name__)

MEMORY_COLLECTION = "memory"
ROADMAP_COLLECTION = "roadmap"
EMBEDDING_DIM = 768

_qdrant_client_instance: Optional[QdrantClient] = None

def get_qdrant_client() -> QdrantClient:
    global _qdrant_client_instance
    if _qdrant_client_instance is not None:
        return _qdrant_client_instance

    try:
        client = QdrantClient(host=settings.QDRANT_HOST, port=settings.QDRANT_PORT, timeout=3.0)
        # Ping Qdrant
        client.get_collections()
        _qdrant_client_instance = client
        logger.info(f"Connected to Qdrant at {settings.QDRANT_HOST}:{settings.QDRANT_PORT}")
    except Exception as e:
        logger.warning(f"Could not connect to Qdrant at {settings.QDRANT_HOST}:{settings.QDRANT_PORT} ({e}). Falling back to in-memory Qdrant Client.")
        _qdrant_client_instance = QdrantClient(":memory:")
    
    init_collections(_qdrant_client_instance)
    return _qdrant_client_instance

def init_collections(client: QdrantClient):
    for col_name in [MEMORY_COLLECTION, ROADMAP_COLLECTION]:
        try:
            cols = [c.name for c in client.get_collections().collections]
            if col_name not in cols:
                client.create_collection(
                    collection_name=col_name,
                    vectors_config=qmodels.VectorParams(
                        size=EMBEDDING_DIM,
                        distance=qmodels.Distance.COSINE
                    )
                )
                logger.info(f"Created Qdrant collection '{col_name}'")
        except Exception as err:
            logger.error(f"Error initializing Qdrant collection '{col_name}': {err}")

def get_embedding(text: str) -> List[float]:
    """
    Generate embedding for text using nomic-embed-text via Ollama API.
    """
    if not text.strip():
        return [0.0] * EMBEDDING_DIM

    try:
        url = f"{settings.OLLAMA_BASE_URL.rstrip('/')}/embeddings"
        payload = {
            "model": settings.OLLAMA_EMBED_MODEL,
            "prompt": text
        }
        with httpx.Client(timeout=5.0) as http:
            resp = http.post(url, json=payload)
            if resp.status_code == 200:
                data = resp.json()
                emb = data.get("embedding")
                if emb and isinstance(emb, list):
                    # Truncate or pad to EMBEDDING_DIM
                    if len(emb) == EMBEDDING_DIM:
                        return emb
                    elif len(emb) > EMBEDDING_DIM:
                        return emb[:EMBEDDING_DIM]
                    else:
                        return emb + [0.0] * (EMBEDDING_DIM - len(emb))
    except Exception as err:
        logger.warning(f"Embedding request failed ({err}). Using fallback vector.")

    # Fallback deterministic pseudo-embedding based on hash if Ollama unavailable
    import hashlib
    h = hashlib.sha256(text.encode("utf-8")).digest()
    vec = [(float(b) / 255.0) - 0.5 for b in h]
    while len(vec) < EMBEDDING_DIM:
        vec.extend(vec)
    return vec[:EMBEDDING_DIM]

def upsert_memory_point(point_id: str, text: str, payload: Dict[str, Any]):
    client = get_qdrant_client()
    vec = get_embedding(text)
    client.upsert(
        collection_name=MEMORY_COLLECTION,
        points=[
            qmodels.PointStruct(
                id=str(uuid.UUID(hashlib.md5(point_id.encode('utf-8')).hexdigest())),
                vector=vec,
                payload=payload
            )
        ]
    )

def search_memory(query: str, limit: int = 5) -> List[Dict[str, Any]]:
    client = get_qdrant_client()
    vec = get_embedding(query)
    try:
        results = client.search(
            collection_name=MEMORY_COLLECTION,
            query_vector=vec,
            limit=limit
        )
        return [{"score": r.score, **r.payload} for r in results]
    except Exception as e:
        logger.error(f"Error searching Qdrant memory: {e}")
        return []
