from collections.abc import Sequence
from uuid import UUID


def recall_at_k(
    retrieved_chunk_ids: Sequence[UUID],
    expected_chunk_ids: Sequence[UUID],
    *,
    k: int = 5,
) -> float:
    expected = set(expected_chunk_ids)
    if not expected:
        return 0.0
    retrieved = set(retrieved_chunk_ids[:k])
    return len(expected & retrieved) / len(expected)


def reciprocal_rank(
    retrieved_chunk_ids: Sequence[UUID],
    expected_chunk_ids: Sequence[UUID],
) -> float:
    expected = set(expected_chunk_ids)
    for rank, chunk_id in enumerate(retrieved_chunk_ids, start=1):
        if chunk_id in expected:
            return 1 / rank
    return 0.0


def mean(values: Sequence[float]) -> float:
    if not values:
        return 0.0
    return sum(values) / len(values)
