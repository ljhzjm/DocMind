"""Version 1 HTTP API routes."""

from fastapi import APIRouter

from app.api.v1.conversations import router as conversations_router
from app.api.v1.documents import router as documents_router
from app.api.v1.eval import router as eval_router
from app.api.v1.eval_versions import router as eval_versions_router
from app.api.v1.search import router as search_router

router = APIRouter()
router.include_router(documents_router)
router.include_router(conversations_router)
router.include_router(search_router)
router.include_router(eval_router)
router.include_router(eval_versions_router)

__all__ = ["router"]
