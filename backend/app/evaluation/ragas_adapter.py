import os
from dataclasses import dataclass

from openai import AsyncOpenAI
from ragas.embeddings import OpenAIEmbeddings
from ragas.llms import llm_factory
from ragas.metrics.collections import AnswerRelevancy, Faithfulness

from app.llm.config import LLMConfig, load_llm_config


class RagasConfigurationError(RuntimeError):
    """RAGAS 所需模型或密钥未配置。"""


@dataclass(frozen=True)
class RagasScores:
    faithfulness: float
    answer_relevance: float


class RagasEvaluator:
    """RAGAS 最小集成：仅启用忠实度与答案相关性。"""

    def __init__(self, config: LLMConfig | None = None) -> None:
        self._config = config or load_llm_config()
        self._faithfulness: Faithfulness | None = None
        self._answer_relevancy: AnswerRelevancy | None = None

    async def score(
        self,
        *,
        question: str,
        answer: str,
        contexts: list[str],
    ) -> RagasScores:
        faithfulness, answer_relevancy = self._build_metrics()
        faithfulness_result = await faithfulness.ascore(
            user_input=question,
            response=answer,
            retrieved_contexts=contexts,
        )
        relevance_result = await answer_relevancy.ascore(
            user_input=question,
            response=answer,
        )
        return RagasScores(
            faithfulness=float(faithfulness_result.value),
            answer_relevance=float(relevance_result.value),
        )

    def _build_metrics(self) -> tuple[Faithfulness, AnswerRelevancy]:
        if self._faithfulness is not None and self._answer_relevancy is not None:
            return self._faithfulness, self._answer_relevancy

        judge_alias = self._config.routes["evaluation_judge"]
        judge = self._config.models[judge_alias]
        judge_provider = self._config.providers[judge.provider]
        judge_client = self._client(
            api_key_env=judge_provider.api_key_env,
            base_url=judge_provider.base_url,
        )
        judge_llm = llm_factory(
            judge.model,
            provider="openai",
            client=judge_client,
        )

        embedding_alias = self._config.routes["embedding"]
        embedding = self._config.models[embedding_alias]
        embedding_provider = self._config.providers[embedding.provider]
        embedding_client = self._client(
            api_key_env=embedding_provider.api_key_env,
            base_url=embedding_provider.base_url,
        )
        embeddings = OpenAIEmbeddings(
            client=embedding_client,
            model=embedding.model,
        )

        self._faithfulness = Faithfulness(llm=judge_llm)
        self._answer_relevancy = AnswerRelevancy(
            llm=judge_llm,
            embeddings=embeddings,
        )
        return self._faithfulness, self._answer_relevancy

    @staticmethod
    def _client(*, api_key_env: str, base_url: str) -> AsyncOpenAI:
        api_key = os.getenv(api_key_env, "")
        if not api_key:
            raise RagasConfigurationError(
                f"environment variable '{api_key_env}' is not set for RAGAS"
            )
        return AsyncOpenAI(api_key=api_key, base_url=base_url)
