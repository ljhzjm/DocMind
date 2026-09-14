from collections.abc import AsyncIterator, Sequence

from pydantic import ValidationError

from app.llm import LLMMessage, LLMProvider, LLMRouter, LLMTask, create_default_router
from app.llm.base import FinishEvent, TextDeltaEvent
from app.rag.answer_stream import CitationFirstAnswerParser
from app.rag.parsing import StructuredOutputError, parse_json_object
from app.rag.prompts import render_prompt
from app.rag.types import (
    AnswerDeltaEvent,
    CitationValidationError,
    DoneEvent,
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

    def _get_provider(self) -> LLMProvider:
        if self._provider is not None:
            return self._provider
        router = self._router or create_default_router()
        route = router.resolve(LLMTask.FINAL_GENERATION)
        self._provider = route.provider
        return self._provider

    async def generate(
        self,
        query: str,
        contexts: Sequence[RAGContext],
        *,
        max_retries: int = 1,
    ) -> RAGAnswer:
        if not contexts:
            raise RAGGenerationError("answer generation requires at least one context")

        provider = self._get_provider()
        validation_error: str | None = None
        attempts = max_retries + 1
        for _ in range(attempts):
            result = await provider.chat(
                self._messages(
                    query,
                    contexts,
                    validation_error=validation_error,
                ),
                task=LLMTask.FINAL_GENERATION.value,
            )
            try:
                return validate_answer(result.text, max_citation=len(contexts))
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

        provider = self._get_provider()
        validation_error: str | None = None
        attempts = max_retries + 1

        for _ in range(attempts):
            parser = CitationFirstAnswerParser(max_citation=len(contexts))
            try:
                async for event in provider.chat_stream(
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
                    elif isinstance(event, FinishEvent):
                        pass

                answer = parser.finish()
                if not answer.answer.strip():
                    raise CitationValidationError("answer must not be empty")
                yield DoneEvent(citations=answer.citations)
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
