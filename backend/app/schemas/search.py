from uuid import UUID

from pydantic import BaseModel, Field

from app.retrieval.types import SearchMode


class SearchResultResponse(BaseModel):
    chunk_id: UUID
    document_id: UUID
    content: str
    document_name: str
    page_number: int | None
    heading_path: list[str]
    score: float
    sources: list[str]


class SearchResponse(BaseModel):
    query: str
    mode: SearchMode
    top_k: int = Field(ge=1)
    results: list[SearchResultResponse]
