from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import get_settings
from app.db.session import get_async_session
from app.llm.base import LLMConfigurationError
from app.retrieval.embedding import EmbeddingError
from app.retrieval.service import SearchService
from app.retrieval.types import SearchMode
from app.schemas.search import SearchResponse, SearchResultResponse

router = APIRouter(prefix="/search", tags=["search"])


def get_search_service() -> SearchService:
    return SearchService()


@router.get("", response_model=SearchResponse)
async def search(
    q: Annotated[str, Query(min_length=1, max_length=2000)],
    session: Annotated[AsyncSession, Depends(get_async_session)],
    service: Annotated[SearchService, Depends(get_search_service)],
    mode: SearchMode = SearchMode.HYBRID,
    top_k: Annotated[int | None, Query(ge=1, le=50)] = None,
) -> SearchResponse:
    """按向量、BM25 或 RRF 混合模式检索知识库切片。"""
    effective_top_k = top_k or get_settings().retrieval_top_k
    try:
        hits = await service.search(
            session,
            query=q,
            mode=mode,
            top_k=effective_top_k,
        )
    except (LLMConfigurationError, EmbeddingError) as exc:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail=str(exc),
        ) from exc

    return SearchResponse(
        query=q,
        mode=mode,
        top_k=effective_top_k,
        results=[
            SearchResultResponse(
                chunk_id=hit.chunk_id,
                document_id=hit.document_id,
                content=hit.content,
                document_name=hit.document_name,
                page_number=hit.page_number,
                heading_path=list(hit.heading_path),
                score=hit.score,
                sources=list(hit.sources),
            )
            for hit in hits
        ],
    )
