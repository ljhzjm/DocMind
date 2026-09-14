from dataclasses import dataclass

from pydantic import BaseModel, Field, ValidationError

from app.llm import LLMMessage, LLMRouter, LLMTask, create_default_router
from app.llm.base import LLMError, TokenUsage
from app.rag.parsing import parse_json_object
from app.rag.prompts import render_prompt


class RewritePayload(BaseModel):
    rewritten_query: str = Field(min_length=1)
    keywords: list[str] = Field(default_factory=list)


@dataclass(frozen=True)
class RewriteResult:
    query: str
    keywords: list[str]
    usage: TokenUsage = TokenUsage()
    model_name: str = "original"

    @property
    def retrieval_query(self) -> str:
        return " ".join([self.query, *self.keywords]).strip()


class QueryRewriter:
    """用便宜模型改写查询；任何失败都降级为原查询。"""

    def __init__(self, router: LLMRouter | None = None) -> None:
        self._router = router or create_default_router()

    async def rewrite(self, query: str) -> RewriteResult:
        try:
            route = self._router.resolve(LLMTask.QUERY_REWRITE)
            result = await route.provider.chat(
                [
                    LLMMessage(
                        role="user",
                        content=render_prompt("query_rewrite.j2", query=query),
                    )
                ],
                task=LLMTask.QUERY_REWRITE.value,
            )
            payload = RewritePayload.model_validate(parse_json_object(result.text))
            keywords = [keyword.strip() for keyword in payload.keywords if keyword.strip()]
            return RewriteResult(
                query=payload.rewritten_query.strip(),
                keywords=keywords,
                usage=result.usage,
                model_name=route.model_name,
            )
        except (LLMError, ValidationError, ValueError, TypeError):
            return RewriteResult(query=query, keywords=[])
