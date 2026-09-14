from collections.abc import Sequence
from dataclasses import dataclass

from pydantic import BaseModel, Field, ValidationError

from app.evaluation.prompts import render_evaluation_prompt
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


class JudgeScorePayload(BaseModel):
    faithfulness: int = Field(ge=1, le=5)
    answer_relevance: int = Field(ge=1, le=5)
    faithfulness_reason: str = Field(min_length=1)
    relevance_reason: str = Field(min_length=1)


@dataclass(frozen=True)
class JudgeResult:
    faithfulness: int
    answer_relevance: int
    usage: TokenUsage
    model_name: str
    estimated_cost: float
    reasons: dict[str, str]


class JudgeFormatError(RuntimeError):
    """Judge 在允许重试后仍未返回合法结构。"""


class JudgeService:
    """使用 LLM-as-Judge 输出 1-5 分结构化评分。"""

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

    async def score(
        self,
        *,
        question: str,
        reference_answer: str,
        answer: str,
        contexts: Sequence[str],
    ) -> JudgeResult:
        route = self._get_route()
        validation_error: str | None = None
        for _ in range(self._max_retries + 1):
            result = await route.provider.chat(
                [
                    LLMMessage(
                        role="user",
                        content=render_evaluation_prompt(
                            "generation_judge.j2",
                            question=question,
                            reference_answer=reference_answer,
                            answer=answer,
                            contexts=contexts,
                            validation_error=validation_error,
                        ),
                    )
                ],
                task=LLMTask.EVALUATION_JUDGE.value,
            )
            try:
                payload = JudgeScorePayload.model_validate(parse_json_object(result.text))
                return JudgeResult(
                    faithfulness=payload.faithfulness,
                    answer_relevance=payload.answer_relevance,
                    usage=result.usage,
                    model_name=route.model_name,
                    estimated_cost=calculate_token_cost(
                        result.usage,
                        input_cost_per_million=route.input_cost_per_million,
                        output_cost_per_million=route.output_cost_per_million,
                    ),
                    reasons={
                        "faithfulness": payload.faithfulness_reason,
                        "answer_relevance": payload.relevance_reason,
                    },
                )
            except (StructuredOutputError, ValidationError) as exc:
                validation_error = str(exc)

        raise JudgeFormatError(
            f"judge returned invalid JSON after {self._max_retries + 1} attempts"
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
