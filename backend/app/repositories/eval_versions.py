import hashlib
import json
from typing import Any

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.eval_dataset import EvalDatasetItem
from app.models.eval_dataset_version import EvalDatasetVersion
from app.repositories.eval import list_eval_cases


def dataset_snapshot(cases: list[EvalDatasetItem]) -> list[dict[str, Any]]:
    """生成稳定、可 JSON 序列化的样本快照。"""
    return [
        {
            "id": str(case.id),
            "question": case.question,
            "reference_answer": case.reference_answer,
            "expected_chunk_ids": [str(chunk_id) for chunk_id in case.expected_chunk_ids],
            "tags": list(case.tags),
        }
        for case in cases
    ]


def dataset_content_hash(snapshot: list[dict[str, Any]]) -> str:
    raw = json.dumps(snapshot, ensure_ascii=False, sort_keys=True, separators=(",", ":"))
    return hashlib.sha256(raw.encode("utf-8")).hexdigest()


async def ensure_dataset_version(
    session: AsyncSession,
    *,
    dataset_name: str,
    created_by: str,
) -> EvalDatasetVersion:
    """冻结当前数据集；内容未变化时复用最近版本。"""
    await session.execute(select(func.pg_advisory_xact_lock(func.hashtext(dataset_name))))
    cases = await list_eval_cases(session, dataset_name)
    snapshot = dataset_snapshot(cases)
    content_hash = dataset_content_hash(snapshot)
    existing = await session.scalar(
        select(EvalDatasetVersion).where(
            EvalDatasetVersion.dataset_name == dataset_name,
            EvalDatasetVersion.content_hash == content_hash,
        )
    )
    if existing is not None:
        return existing

    latest_revision = await session.scalar(
        select(func.coalesce(func.max(EvalDatasetVersion.revision), 0)).where(
            EvalDatasetVersion.dataset_name == dataset_name
        )
    )
    version = EvalDatasetVersion(
        dataset_name=dataset_name,
        revision=int(latest_revision or 0) + 1,
        content_hash=content_hash,
        case_count=len(snapshot),
        snapshot=snapshot,
        created_by=created_by,
    )
    session.add(version)
    await session.commit()
    await session.refresh(version)
    return version


async def list_dataset_versions(
    session: AsyncSession,
    dataset_name: str,
) -> list[EvalDatasetVersion]:
    result = await session.scalars(
        select(EvalDatasetVersion)
        .where(EvalDatasetVersion.dataset_name == dataset_name)
        .order_by(EvalDatasetVersion.revision.desc())
    )
    return list(result.all())
