from collections.abc import Sequence
from time import perf_counter

from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import Settings, get_settings
from app.evaluation.judge import JudgeFormatError, JudgeService
from app.evaluation.metrics import mean, recall_at_k, reciprocal_rank
from app.evaluation.ragas_adapter import (
    RagasConfigurationError,
    RagasEvaluator,
    RagasScores,
)
from app.evaluation.types import (
    CaseMetrics,
    ConfigMetrics,
    EvalCase,
    RetrievalConfig,
)
from app.rag.answer import AnswerGenerator, RAGGenerationError
from app.rag.rerank import RerankProvider, create_reranker
from app.rag.types import RAGContext
from app.retrieval.service import SearchService


class EvaluationRunner:
    """执行多检索配置的检索与生成评测。"""

    def __init__(
        self,
        *,
        settings: Settings | None = None,
        search_service: SearchService | None = None,
        reranker: RerankProvider | None = None,
        answer_generator: AnswerGenerator | None = None,
        judge: JudgeService | None = None,
        ragas_evaluator: RagasEvaluator | None = None,
    ) -> None:
        self._settings = settings or get_settings()
        self._search_service = search_service or SearchService()
        self._reranker = reranker or create_reranker(self._settings)
        self._answer_generator = answer_generator or AnswerGenerator()
        self._judge = judge or JudgeService()
        self._ragas = ragas_evaluator or RagasEvaluator()

    async def run(
        self,
        session: AsyncSession,
        *,
        cases: Sequence[EvalCase],
        configs: Sequence[RetrievalConfig],
    ) -> list[ConfigMetrics]:
        return [await self._run_config(session, cases=cases, config=config) for config in configs]

    async def _run_config(
        self,
        session: AsyncSession,
        *,
        cases: Sequence[EvalCase],
        config: RetrievalConfig,
    ) -> ConfigMetrics:
        results = [await self._run_case(session, case=case, config=config) for case in cases]
        ragas_faithfulness = [
            result.ragas_faithfulness for result in results if result.ragas_faithfulness is not None
        ]
        ragas_relevance = [
            result.ragas_answer_relevance
            for result in results
            if result.ragas_answer_relevance is not None
        ]
        return ConfigMetrics(
            config=config,
            case_count=len(results),
            recall_at_5=mean([result.recall_at_5 for result in results]),
            mrr=mean([result.reciprocal_rank for result in results]),
            faithfulness=mean([result.faithfulness for result in results]),
            answer_relevance=mean([result.answer_relevance for result in results]),
            ragas_faithfulness=(mean(ragas_faithfulness) if ragas_faithfulness else None),
            ragas_answer_relevance=(mean(ragas_relevance) if ragas_relevance else None),
            average_latency_ms=mean([result.latency_ms for result in results]),
            average_estimated_cost=mean([result.estimated_cost for result in results]),
            cases=results,
        )

    async def _run_case(
        self,
        session: AsyncSession,
        *,
        case: EvalCase,
        config: RetrievalConfig,
    ) -> CaseMetrics:
        started_at = perf_counter()
        hits = await self._search_service.search(
            session,
            query=case.question,
            mode=config.mode,
            top_k=config.top_k,
        )
        if config.rerank:
            hits = await self._reranker.rerank(
                case.question,
                hits,
                top_k=config.top_k,
            )

        retrieved_ids = [hit.chunk_id for hit in hits]
        recall = recall_at_k(
            retrieved_ids,
            case.expected_chunk_ids,
            k=5,
        )
        mrr = reciprocal_rank(retrieved_ids, case.expected_chunk_ids)
        contexts = hits[:5]
        if not contexts:
            return CaseMetrics(
                question=case.question,
                recall_at_5=recall,
                reciprocal_rank=mrr,
                faithfulness=0,
                answer_relevance=0,
                ragas_faithfulness=None,
                ragas_answer_relevance=None,
                latency_ms=self._elapsed_ms(started_at),
                estimated_cost=0,
                error="empty retrieval result",
            )

        rag_contexts = [
            RAGContext(citation_number=index, hit=hit)
            for index, hit in enumerate(contexts, start=1)
        ]
        try:
            generation = await self._answer_generator.generate_with_metadata(
                case.question,
                rag_contexts,
            )
            judge = await self._judge.score(
                question=case.question,
                reference_answer=case.reference_answer,
                answer=generation.answer.answer,
                contexts=[hit.content for hit in contexts],
            )
        except (RAGGenerationError, JudgeFormatError) as exc:
            return CaseMetrics(
                question=case.question,
                recall_at_5=recall,
                reciprocal_rank=mrr,
                faithfulness=0,
                answer_relevance=0,
                ragas_faithfulness=None,
                ragas_answer_relevance=None,
                latency_ms=self._elapsed_ms(started_at),
                estimated_cost=0,
                error=str(exc),
            )

        ragas_scores: RagasScores | None = None
        ragas_error: str | None = None
        try:
            ragas_scores = await self._ragas.score(
                question=case.question,
                answer=generation.answer.answer,
                contexts=[hit.content for hit in contexts],
            )
        except RagasConfigurationError as exc:
            ragas_error = str(exc)

        estimated_cost = generation.estimated_cost + judge.estimated_cost
        return CaseMetrics(
            question=case.question,
            recall_at_5=recall,
            reciprocal_rank=mrr,
            faithfulness=judge.faithfulness,
            answer_relevance=judge.answer_relevance,
            ragas_faithfulness=(ragas_scores.faithfulness if ragas_scores is not None else None),
            ragas_answer_relevance=(
                ragas_scores.answer_relevance if ragas_scores is not None else None
            ),
            latency_ms=self._elapsed_ms(started_at),
            estimated_cost=estimated_cost,
            error=ragas_error,
        )

    @staticmethod
    def _elapsed_ms(started_at: float) -> float:
        return round((perf_counter() - started_at) * 1000, 3)
