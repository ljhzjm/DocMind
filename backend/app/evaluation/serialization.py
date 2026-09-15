from typing import Any

from app.evaluation.types import ConfigMetrics
from app.schemas.evaluation import CaseMetricsResponse, ConfigMetricsResponse


def config_metrics_payload(result: ConfigMetrics) -> dict[str, Any]:
    """把领域指标转换为稳定 JSONB 结构，供异步任务和 API 共用。"""
    response = ConfigMetricsResponse(
        name=result.config.name,
        mode=result.config.mode,
        top_k=result.config.top_k,
        rerank=result.config.rerank,
        case_count=result.case_count,
        recall_at_5=result.recall_at_5,
        mrr=result.mrr,
        faithfulness=result.faithfulness,
        answer_relevance=result.answer_relevance,
        ragas_faithfulness=result.ragas_faithfulness,
        ragas_answer_relevance=result.ragas_answer_relevance,
        average_latency_ms=result.average_latency_ms,
        average_first_token_latency_ms=result.average_first_token_latency_ms,
        average_input_tokens=result.average_input_tokens,
        average_output_tokens=result.average_output_tokens,
        average_estimated_cost=result.average_estimated_cost,
        refusal_rate=result.refusal_rate,
        hallucination_risk=result.hallucination_risk,
        cases=[
            CaseMetricsResponse(
                question=case.question,
                recall_at_5=case.recall_at_5,
                reciprocal_rank=case.reciprocal_rank,
                faithfulness=case.faithfulness,
                answer_relevance=case.answer_relevance,
                ragas_faithfulness=case.ragas_faithfulness,
                ragas_answer_relevance=case.ragas_answer_relevance,
                latency_ms=case.latency_ms,
                first_token_latency_ms=case.first_token_latency_ms,
                input_tokens=case.input_tokens,
                output_tokens=case.output_tokens,
                estimated_cost=case.estimated_cost,
                refused=case.refused,
                error=case.error,
            )
            for case in result.cases
        ],
    )
    return response.model_dump(mode="json")
