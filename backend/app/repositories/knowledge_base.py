from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import Session

from app.models.knowledge_base import KnowledgeBaseRevision

_REVISION_ID = 1


async def get_knowledge_base_revision(session: AsyncSession) -> int:
    record = await session.get(KnowledgeBaseRevision, _REVISION_ID)
    return record.revision if record is not None else 0


async def bump_knowledge_base_revision(session: AsyncSession) -> int:
    record = await session.get(KnowledgeBaseRevision, _REVISION_ID, with_for_update=True)
    if record is None:
        record = KnowledgeBaseRevision(id=_REVISION_ID, revision=1)
        session.add(record)
    else:
        record.revision += 1
    await session.commit()
    return record.revision


def bump_knowledge_base_revision_sync(session: Session) -> int:
    record = session.get(
        KnowledgeBaseRevision,
        _REVISION_ID,
        with_for_update=True,
    )
    if record is None:
        record = KnowledgeBaseRevision(id=_REVISION_ID, revision=1)
        session.add(record)
    else:
        record.revision += 1
    session.commit()
    return record.revision
