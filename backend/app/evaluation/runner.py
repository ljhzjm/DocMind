from collections.abc import Awaitable, Callable, Sequence
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
    EvaluationCheckpoint,
    EvaluationProgress,
    RetrievalConfig,
)
from app.rag.answer import AnswerGenerator, RAGGenerationError
from app.rag.rerank import RerankProvider, create_reranker
from app.rag.types import AnswerDeltaEvent, DoneEvent, RAGContext
from app.retrieval.service import SearchService

ProgressCallback = Callable[[EvaluationProgress], Awaitable[None]]


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
        progress_callback: ProgressCallback | None = None,
        checkpoint: Sequence[EvaluationCheckpoint] = (),
    ) -> list[ConfigMetrics]:
        total = len(cases) * len(configs)
        completed_by_config: dict[int, list[CaseMetrics]] = {}
        for item in checkpoint:
            completed_by_config.setdefault(item.config_index, []).append(item.metrics)
        completed = sum(len(items) for items in completed_by_config.values())

        results: list[ConfigMetrics] = []
        for config_index, config in enumerate(configs):
            config_results = completed_by_config.get(config_index, [])
            results.append(
                await self._run_config(
                    session,
                    cases=cases,
                    config=config,
                    completed_results=config_results,
                    on_case_complete=self._progress_reporter(
                        progress_callback,
                        config_index=config_index,
                        completed=completed,
                        total=total,
                    ),
                )
            )
            completed += len(cases) - len(config_results)
        return results

    @staticmethod
    def _progress_reporter(
        callback: ProgressCallback | None,
        *,
        config_index: int,
        completed: int,
        total: int,
    ) -> Callable[[int, CaseMetrics], Awaitable[None]] | None:
        if callback is None:
            return None
        current = completed

        async def report(case_index: int, metrics: CaseMetrics) -> None:
            nonlocal current
            current += 1
            await callback(
                EvaluationProgress(
                    completed=current,
                    total=total,
                    config_index=config_index,
                    case_index=case_index,
                    metrics=metrics,
                )
            )

        return report

    async def _run_config(
        self,
        session: AsyncSession,
        *,
        cases: Sequence[EvalCase],
        config: RetrievalConfig,
        completed_results: Sequence[CaseMetrics] = (),
        on_case_complete: Callable[[int, CaseMetrics], Awaitable[None]] | None = None,
    ) -> ConfigMetrics:
        results = list(completed_results)
        for case_index, case in enumerate(cases):
            if case_index < len(completed_results):
                continue
            metrics = await self._run_case(session, case=case, config=config)
            results.append(metrics)
            if on_case_complete is not None:
                await on_case_complete(case_index, metrics)
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
            average_first_token_latency_ms=mean(
                [result.first_token_latency_ms for result in results]
            ),
            average_input_tokens=mean([result.input_tokens for result in results]),
            average_output_tokens=mean([result.output_tokens for result in results]),
            average_estimated_cost=mean([result.estimated_cost for result in results]),
            refusal_rate=mean([1.0 if result.refused else 0.0 for result in results]),
            hallucination_risk=mean([self._hallucination_risk(result) for result in results]),
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
                first_token_latency_ms=0,
                input_tokens=0,
                output_tokens=0,
                estimated_cost=0,
                refused=True,
                error="empty retrieval result",
            )

        rag_contexts = [
            RAGContext(citation_number=index, hit=hit)
            for index, hit in enumerate(contexts, start=1)
        ]
        generated_text = ""
        first_token_latency_ms = 0.0
        done_event: DoneEvent | None = None
        try:
            async for event in self._answer_generator.stream(
                case.question,
                rag_contexts,
            ):
                if isinstance(event, AnswerDeltaEvent):
                    if first_token_latency_ms == 0:
                        first_token_latency_ms = self._elapsed_ms(started_at)
                    generated_text += event.delta
                elif isinstance(event, DoneEvent):
                    done_event = event
            if done_event is None:
                raise RAGGenerationError("generation stream ended without completion")
            judge = await self._judge.score(
                question=case.question,
                reference_answer=case.reference_answer,
                answer=generated_text,
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
                first_token_latency_ms=first_token_latency_ms,
                input_tokens=0,
                output_tokens=0,
                estimated_cost=0,
                refused=False,
                error=str(exc),
            )

        ragas_scores: RagasScores | None = None
        ragas_error: str | None = None
        try:
            ragas_scores = await self._ragas.score(
                question=case.question,
                answer=generated_text,
                contexts=[hit.content for hit in contexts],
            )
        except RagasConfigurationError as exc:
            ragas_error = str(exc)

        estimated_cost = done_event.estimated_cost + judge.estimated_cost
        refused = generated_text.strip() == "未找到相关资料"
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
            first_token_latency_ms=first_token_latency_ms,
            input_tokens=done_event.usage.input_tokens,
            output_tokens=done_event.usage.output_tokens,
            estimated_cost=estimated_cost,
            refused=refused,
            error=ragas_error,
        )

    @staticmethod
    def _elapsed_ms(started_at: float) -> float:
        return round((perf_counter() - started_at) * 1000, 3)

    @staticmethod
    def _hallucination_risk(result: CaseMetrics) -> float:
        if result.ragas_faithfulness is not None:
            return max(0.0, 1.0 - result.ragas_faithfulness)
        return max(0.0, 1.0 - result.faithfulness / 5)
