from enum import StrEnum
from typing import TypeVar


class DocumentStatus(StrEnum):
    """文档解析生命周期。"""

    UPLOADED = "uploaded"
    PARSING = "parsing"
    READY = "ready"
    FAILED = "failed"


class MessageRole(StrEnum):
    """会话消息角色。"""

    USER = "user"
    ASSISTANT = "assistant"


class UsageStep(StrEnum):
    """成本面板与评测关注的 LLM/RAG 步骤。"""

    REWRITE = "rewrite"
    RETRIEVE = "retrieve"
    GENERATE = "generate"


EnumType = TypeVar("EnumType", bound=StrEnum)


def enum_values(enum_type: type[EnumType]) -> list[str]:
    """将 Python 枚举值传给 PostgreSQL，避免写入成员名而非业务值。"""
    return [member.value for member in enum_type]
