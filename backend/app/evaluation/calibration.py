from collections.abc import Sequence
from dataclasses import dataclass

from sqlalchemy.ext.asyncio import AsyncSession

from app.evaluation.types import EvalCase, RetrievalConfig
from app.rag.rerank import RerankProvider
from app.retrieval.service import SearchService


@dataclass(frozen=True)
class ThresholdObservation:
    score: float
    answerable: bool


@dataclass(frozen=True)
class ThresholdCalibration:
    threshold: float
    sample_count: int
    positive_count: int
    negative_count: int
    precision: float
    recall: float
    f1: float
    balanced_accuracy: float
    false_refusal_rate: float
    false_answer_rate: float

    def metrics(self) -> dict[str, float | int]:
        return {
            "precision": self.precision,
            "recall": self.recall,
            "f1": self.f1,
            "balanced_accuracy": self.balanced_accuracy,
            "false_refusal_rate": self.false_refusal_rate,
            "false_answer_rate": self.false_answer_rate,
        }


def choose_refusal_threshold(
    observations: Sequence[ThresholdObservation],
) -> ThresholdCalibration:
    """在候选分数上选择 F1 最高的拒答阈值。"""
    if not observations:
        raise ValueError("threshold calibration requires at least one observation")
    positives = sum(item.answerable for item in observations)
    negatives = len(observations) - positives
    if positives == 0 or negatives == 0:
        raise ValueError("threshold calibration requires positive and negative samples")

    candidates = sorted(
        {
            0.0,
            max(item.score for item in observations) + 1e-9,
            *(item.score for item in observations),
        }
    )
    best: ThresholdCalibration | None = None
    best_key: tuple[float, float, float] | None = None
    for threshold in candidates:
        true_positive = sum(item.answerable and item.score >= threshold for item in observations)
        false_positive = sum(
            not item.answerable and item.score >= threshold for item in observations
        )
        false_negative = positives - true_positive
        true_negative = negatives - false_positive
        precision = true_positive / max(1, true_positive + false_positive)
        recall = true_positive / positives
        false_refusal_rate = false_negative / positives
        false_answer_rate = false_positive / negatives
        f1 = 2 * precision * recall / max(1e-12, precision + recall)
        specificity = true_negative / negatives
        balanced_accuracy = (recall + specificity) / 2
        key = (f1, balanced_accuracy, threshold)
        if best_key is None or key > best_key:
            best_key = key
            best = ThresholdCalibration(
                threshold=threshold,
                sample_count=len(observations),
                positive_count=positives,
                negative_count=negatives,
                precision=precision,
                recall=recall,
                f1=f1,
                balanced_accuracy=balanced_accuracy,
                false_refusal_rate=false_refusal_rate,
                false_answer_rate=false_answer_rate,
            )

    if best is None:
        raise ValueError("could not calibrate threshold")
    return best


async def calibrate_refusal_threshold(
    session: AsyncSession,
    *,
    cases: Sequence[EvalCase],
    config: RetrievalConfig,
    search_service: SearchService | None = None,
    reranker: RerankProvider | None = None,
) -> ThresholdCalibration:
    """跑一遍检索，以 expected chunk 是否命中作为可回答标签。"""
    active_search = search_service or SearchService()
    observations: list[ThresholdObservation] = []
    for case in cases:
        hits = await active_search.search(
            session,
            query=case.question,
            mode=config.mode,
            top_k=config.top_k,
        )
        if config.rerank and reranker is not None:
            hits = await reranker.rerank(case.question, hits, top_k=config.top_k)
        retrieved_ids = {hit.chunk_id for hit in hits}
        answerable = bool(retrieved_ids.intersection(case.expected_chunk_ids))
        observations.append(
            ThresholdObservation(
                score=hits[0].score if hits else 0.0,
                answerable=answerable,
            )
        )
    return choose_refusal_threshold(observations)
