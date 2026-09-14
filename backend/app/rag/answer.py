from collections.abc import AsyncIterator, Sequence

from pydantic import ValidationError

from app.llm import LLMMessage, LLMProvider, LLMRouter, LLMTask, RoutedModel, create_default_router
from app.llm.base import FinishEvent, TextDeltaEvent, TokenUsage, UsageEvent
from app.llm.cost import calculate_token_cost
from app.rag.answer_stream import CitationFirstAnswerParser
from app.rag.parsing import StructuredOutputError, parse_json_object
from app.rag.prompts import render_prompt
from app.rag.types import (
    AnswerDeltaEvent,
    CitationValidationError,
    DoneEvent,
    GenerationOutcome,
    RAGAnswer,
    RAGContext,
)


class RAGGenerationError(RuntimeError):
    """模型在允许的重试次数内仍未返回合法结构。"""


def validate_answer(text: str, *, max_citation: int) -> RAGAnswer:
    """解析并校验 answer/citations，引用编号必须位于 1..max_citation。"""
    payload = RAGAnswer.model_validate(parse_json_object(text))
    answer = payload.answer.strip()
    if not answer:
        raise CitationValidationError("answer must not be empty")

    invalid = [number for number in payload.citations if number < 1 or number > max_citation]
    if invalid:
        raise CitationValidationError(f"citation numbers out of range 1..{max_citation}: {invalid}")
    return RAGAnswer(answer=answer, citations=list(dict.fromkeys(payload.citations)))


class AnswerGenerator:
    """生成结构化答案，引用校验失败时自动重试一次。"""

    def __init__(
        self,
        router: LLMRouter | None = None,
        provider: LLMProvider | None = None,
    ) -> None:
        self._router = router
        self._provider = provider
        self._route: RoutedModel | None = None

    def _get_route(self) -> RoutedModel:
        if self._route is not None:
            return self._route
        if self._provider is not None:
            self._route = RoutedModel(
                task=LLMTask.FINAL_GENERATION,
                alias="injected",
                provider_name="injected",
                model_name="injected",
                input_cost_per_million=0,
                output_cost_per_million=0,
                provider=self._provider,
            )
            return self._route
        router = self._router or create_default_router()
        self._route = router.resolve(LLMTask.FINAL_GENERATION)
        return self._route

    def _get_provider(self) -> LLMProvider:
        return self._get_route().provider

    async def generate(
        self,
        query: str,
        contexts: Sequence[RAGContext],
        *,
        max_retries: int = 1,
    ) -> RAGAnswer:
        outcome = await self.generate_with_metadata(
            query,
            contexts,
            max_retries=max_retries,
        )
        return outcome.answer

    async def generate_with_metadata(
        self,
        query: str,
        contexts: Sequence[RAGContext],
        *,
        max_retries: int = 1,
    ) -> GenerationOutcome:
        if not contexts:
            raise RAGGenerationError("answer generation requires at least one context")

        route = self._get_route()
        validation_error: str | None = None
        attempts = max_retries + 1
        for _ in range(attempts):
            result = await route.provider.chat(
                self._messages(
                    query,
                    contexts,
                    validation_error=validation_error,
                ),
                task=LLMTask.FINAL_GENERATION.value,
            )
            try:
                answer = validate_answer(result.text, max_citation=len(contexts))
                return GenerationOutcome(
                    answer=answer,
                    usage=result.usage,
                    model_name=route.model_name,
                    estimated_cost=calculate_token_cost(
                        result.usage,
                        input_cost_per_million=route.input_cost_per_million,
                        output_cost_per_million=route.output_cost_per_million,
                    ),
                )
            except (StructuredOutputError, ValidationError, CitationValidationError) as exc:
                validation_error = str(exc)

        raise RAGGenerationError(f"model returned invalid citations after {attempts} attempts")

    async def stream(
        self,
        query: str,
        contexts: Sequence[RAGContext],
        *,
        max_retries: int = 1,
    ) -> AsyncIterator[AnswerDeltaEvent | DoneEvent]:
        """先校验流中的 citations，再边接收 answer JSON 字符串边发送增量。"""
        if not contexts:
            raise RAGGenerationError("answer generation requires at least one context")

        route = self._get_route()
        validation_error: str | None = None
        attempts = max_retries + 1

        for _ in range(attempts):
            parser = CitationFirstAnswerParser(max_citation=len(contexts))
            stream_usage = TokenUsage()
            try:
                async for event in route.provider.chat_stream(
                    self._messages(
                        query,
                        contexts,
                        validation_error=validation_error,
                    ),
                    task=LLMTask.FINAL_GENERATION.value,
                ):
                    if isinstance(event, TextDeltaEvent):
                        delta = parser.consume(event.text)
                        if delta:
                            yield AnswerDeltaEvent(delta=delta)
                    elif isinstance(event, UsageEvent):
                        stream_usage = event.usage
                    elif isinstance(event, FinishEvent):
                        if event.usage is not None:
                            stream_usage = event.usage

                answer = parser.finish()
                if not answer.answer.strip():
                    raise CitationValidationError("answer must not be empty")
                yield DoneEvent(
                    citations=answer.citations,
                    usage=stream_usage,
                    model_name=route.model_name,
                )
                return
            except (
                StructuredOutputError,
                ValidationError,
                CitationValidationError,
            ) as exc:
                if parser.answer_emitted:
                    raise RAGGenerationError(
                        "stream failed after answer deltas were emitted"
                    ) from exc
                validation_error = str(exc)

        raise RAGGenerationError(f"model returned invalid citations after {attempts} attempts")

    @staticmethod
    def _messages(
        query: str,
        contexts: Sequence[RAGContext],
        *,
        validation_error: str | None,
    ) -> list[LLMMessage]:
        return [
            LLMMessage(
                role="user",
                content=render_prompt(
                    "rag_answer.j2",
                    query=query,
                    contexts=contexts,
                    max_citation=len(contexts),
                    validation_error=validation_error,
                ),
            )
        ]
