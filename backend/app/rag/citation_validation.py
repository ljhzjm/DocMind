from collections.abc import Sequence
from dataclasses import dataclass

from pydantic import BaseModel, Field, ValidationError

from app.llm import (
    LLMMessage,
    LLMProvider,
    LLMRouter,
    LLMTask,
    RoutedModel,
    create_default_router,
)
from app.llm.base import TokenUsage
from app.llm.cost import calculate_token_cost
from app.rag.parsing import StructuredOutputError, parse_json_object
from app.rag.prompts import render_prompt
from app.rag.types import RAGContext


class CitationSupportItem(BaseModel):
    sentence: str = Field(min_length=1)
    citations: list[int] = Field(default_factory=list)
    supported: bool
    reason: str = Field(min_length=1)


class CitationValidationPayload(BaseModel):
    sentences: list[CitationSupportItem] = Field(min_length=1)


@dataclass(frozen=True)
class CitationValidationResult:
    valid: bool
    unsupported_sentences: tuple[str, ...]
    usage: TokenUsage
    model_name: str
    estimated_cost: float


class CitationValidationError(RuntimeError):
    """引用语义校验返回不可用结果。"""


class CitationSemanticValidator:
    """通过 LLM 判断每句话是否被其引用片段直接支持。"""

    def __init__(
        self,
        *,
        router: LLMRouter | None = None,
        provider: LLMProvider | None = None,
        max_retries: int = 1,
    ) -> None:
        self._router = router
        self._provider = provider
        self._max_retries = max_retries
        self._route: RoutedModel | None = None

    async def validate(
        self,
        *,
        question: str,
        answer: str,
        contexts: Sequence[RAGContext],
    ) -> CitationValidationResult:
        route = self._get_route()
        validation_error: str | None = None
        for _ in range(self._max_retries + 1):
            result = await route.provider.chat(
                [
                    LLMMessage(
                        role="user",
                        content=render_prompt(
                            "citation_validation.j2",
                            question=question,
                            answer=answer,
                            contexts=contexts,
                            validation_error=validation_error,
                        ),
                    )
                ],
                task=LLMTask.EVALUATION_JUDGE.value,
                temperature=0.0,
                max_tokens=2000,
            )
            try:
                payload = CitationValidationPayload.model_validate(parse_json_object(result.text))
                invalid = [
                    citation
                    for item in payload.sentences
                    for citation in item.citations
                    if citation < 1 or citation > len(contexts)
                ]
                if invalid:
                    raise ValueError(f"citation numbers out of range: {invalid}")
                unsupported = tuple(
                    item.sentence for item in payload.sentences if not item.supported
                )
                return CitationValidationResult(
                    valid=not unsupported,
                    unsupported_sentences=unsupported,
                    usage=result.usage,
                    model_name=route.model_name,
                    estimated_cost=calculate_token_cost(
                        result.usage,
                        input_cost_per_million=route.input_cost_per_million,
                        output_cost_per_million=route.output_cost_per_million,
                    ),
                )
            except (StructuredOutputError, ValidationError, ValueError) as exc:
                validation_error = str(exc)

        raise CitationValidationError(
            f"citation validator returned invalid JSON after {self._max_retries + 1} attempts"
        )

    def _get_route(self) -> RoutedModel:
        if self._route is not None:
            return self._route
        if self._provider is not None:
            self._route = RoutedModel(
                task=LLMTask.EVALUATION_JUDGE,
                alias="injected",
                provider_name="injected",
                model_name="injected",
                input_cost_per_million=0,
                output_cost_per_million=0,
                provider=self._provider,
            )
            return self._route
        router = self._router or create_default_router()
        self._route = router.resolve(LLMTask.EVALUATION_JUDGE)
        return self._route
