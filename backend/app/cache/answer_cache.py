import hashlib

from pydantic import BaseModel
from redis.asyncio import Redis
from redis.exceptions import RedisError
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import get_settings
from app.core.redis import get_redis
from app.models.document import Document
from app.models.enums import DocumentStatus
from app.repositories.knowledge_base import get_knowledge_base_revision


class CachedContext(BaseModel):
    citation_number: int
    chunk_id: str
    document_id: str
    content: str
    document_name: str
    page_number: int | None
    heading_path: list[str]
    score: float


class CachedAnswer(BaseModel):
    query: str
    rewritten_query: str
    answer: str
    citations: list[int]
    contexts: list[CachedContext]
    trace_id: str


def normalize_query(query: str) -> str:
    return " ".join(query.strip().lower().split())


def cache_key(
    *,
    query: str,
    knowledge_base_version: str,
    retrieval_config: str,
) -> str:
    raw = "\n".join(
        [
            normalize_query(query),
            knowledge_base_version,
            retrieval_config,
        ]
    )
    return f"answer:v2:{hashlib.sha256(raw.encode()).hexdigest()}"


async def knowledge_base_version(session: AsyncSession) -> str:
    revision = await get_knowledge_base_revision(session)
    if revision > 0:
        return f"revision-{revision}"
    row = (
        await session.execute(
            select(
                func.count(Document.id),
                func.coalesce(func.sum(Document.chunk_count), 0),
                func.max(Document.created_at),
            ).where(Document.status == DocumentStatus.READY)
        )
    ).one()
    raw = f"{row[0]}:{row[1]}:{row[2]}"
    return hashlib.sha256(raw.encode()).hexdigest()[:16]


class AnswerCache:
    def __init__(self, redis: Redis | None = None) -> None:
        self._redis = redis

    async def get(self, key: str) -> CachedAnswer | None:
        if not get_settings().answer_cache_enabled:
            return None
        try:
            value = await self._client().get(key)
        except (RedisError, OSError):
            return None
        if value is None:
            return None
        return CachedAnswer.model_validate_json(value)

    async def set(self, key: str, answer: CachedAnswer) -> None:
        if not get_settings().answer_cache_enabled:
            return
        try:
            await self._client().setex(
                key,
                get_settings().answer_cache_ttl_seconds,
                answer.model_dump_json(),
            )
        except (RedisError, OSError):
            return

    def _client(self) -> Redis:
        return self._redis or get_redis()
