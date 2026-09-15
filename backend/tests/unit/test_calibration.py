import pytest
from app.core.config import Settings
from app.evaluation.calibration import (
    ThresholdObservation,
    choose_refusal_threshold,
)
from app.rag.refusal import rerank_provider_key


def test_choose_refusal_threshold_maximizes_f1() -> None:
    result = choose_refusal_threshold(
        [
            ThresholdObservation(score=0.8, answerable=True),
            ThresholdObservation(score=0.6, answerable=True),
            ThresholdObservation(score=0.2, answerable=False),
            ThresholdObservation(score=0.1, answerable=False),
        ]
    )

    assert result.threshold == 0.6
    assert result.precision == 1.0
    assert result.recall == 1.0
    assert result.f1 == 1.0
    assert result.false_refusal_rate == 0.0
    assert result.false_answer_rate == 0.0


def test_choose_refusal_threshold_requires_both_classes() -> None:
    with pytest.raises(ValueError, match="positive and negative"):
        choose_refusal_threshold([ThresholdObservation(score=0.9, answerable=True)])


def test_rerank_provider_key_reflects_effective_configuration() -> None:
    settings = Settings(rerank_enabled=True, rerank_provider="llm")

    assert rerank_provider_key(settings, rerank_enabled=True) == "llm"
    assert rerank_provider_key(settings, rerank_enabled=False) == "none"
    assert (
        rerank_provider_key(
            Settings(rerank_enabled=False, rerank_provider="llm"),
            rerank_enabled=True,
        )
        == "none"
    )
