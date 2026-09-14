from collections.abc import Sequence
from dataclasses import replace
from uuid import UUID

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.document import Chunk
from app.retrieval.types import RetrievalHit


async def expand_parent_hits(
    session: AsyncSession,
    hits: Sequence[RetrievalHit],
) -> list[RetrievalHit]:
    """命中叶子块后，用父块内容替换展示内容，保留子块分数和 ID。"""
    if not hits:
        return []
    chunk_ids = [hit.chunk_id for hit in hits]
    rows = (
        await session.execute(
            select(Chunk.id, Chunk.parent_chunk_id).where(Chunk.id.in_(chunk_ids))
        )
    ).all()
    parent_by_child = {chunk_id: parent_id for chunk_id, parent_id in rows if parent_id is not None}
    parent_ids = list(set(parent_by_child.values()))
    if not parent_ids:
        return list(hits)
    parent_contents: dict[UUID, str] = {}
    for parent_id, content in (
        await session.execute(select(Chunk.id, Chunk.content).where(Chunk.id.in_(parent_ids)))
    ).all():
        parent_contents[parent_id] = content
    expanded: list[RetrievalHit] = []
    for hit in hits:
        parent_id = parent_by_child.get(hit.chunk_id)
        parent_content = parent_contents.get(parent_id) if parent_id else None
        if parent_content is None:
            expanded.append(hit)
            continue
        expanded.append(
            replace(
                hit,
                content=parent_content,
                sources=tuple(sorted({*hit.sources, "parent"})),
            )
        )
    return expanded
