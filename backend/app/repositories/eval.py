from uuid import UUID

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.eval_dataset import EvalDatasetItem


async def list_eval_dataset_summaries(
    session: AsyncSession,
) -> list[tuple[str, int]]:
    rows = (
        await session.execute(
            select(
                EvalDatasetItem.dataset_name,
                func.count(EvalDatasetItem.id),
            )
            .group_by(EvalDatasetItem.dataset_name)
            .order_by(EvalDatasetItem.dataset_name)
        )
    ).all()
    return [(str(name), int(count)) for name, count in rows]


async def list_eval_cases(
    session: AsyncSession,
    dataset_name: str,
) -> list[EvalDatasetItem]:
    result = await session.scalars(
        select(EvalDatasetItem)
        .where(EvalDatasetItem.dataset_name == dataset_name)
        .order_by(EvalDatasetItem.created_at, EvalDatasetItem.id)
    )
    return list(result.all())


async def create_eval_case(
    session: AsyncSession,
    *,
    dataset_name: str,
    question: str,
    reference_answer: str,
    expected_chunk_ids: list[UUID],
    tags: list[str],
    created_by: str,
) -> EvalDatasetItem:
    case = EvalDatasetItem(
        dataset_name=dataset_name,
        question=question,
        reference_answer=reference_answer,
        expected_chunk_ids=expected_chunk_ids,
        tags=tags,
        created_by=created_by,
    )
    session.add(case)
    await session.commit()
    await session.refresh(case)
    return case
