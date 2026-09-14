from uuid import UUID

from pydantic import BaseModel, ConfigDict

from app.models.enums import DocumentStatus


class DocumentUploadResponse(BaseModel):
    """上传接口返回，任务 ID 由文档 UUID 生成以便统一轮询。"""

    document_id: UUID
    task_id: str
    status: DocumentStatus


class DocumentStatusResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    document_id: UUID
    filename: str
    status: DocumentStatus
    chunk_count: int
