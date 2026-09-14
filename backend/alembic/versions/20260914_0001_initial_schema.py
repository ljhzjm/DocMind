"""initial DocMind knowledge base schema

Revision ID: 20260914_0001
Revises:
Create Date: 2026-09-14 17:30:00
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from pgvector.sqlalchemy import Vector
from sqlalchemy.dialects import postgresql

revision: str = "20260914_0001"
down_revision: str | None = None
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    # 向量类型依赖 pgvector 扩展。扩展是数据库级能力，降级时不删除。
    op.execute("CREATE EXTENSION IF NOT EXISTS vector")

    # 使用 PostgreSQL 原生 ENUM，确保文档状态、消息角色和用量步骤无法写入脏值。
    document_status = postgresql.ENUM(
        "uploaded",
        "parsing",
        "ready",
        "failed",
        name="document_status",
    )
    message_role = postgresql.ENUM("user", "assistant", name="message_role")
    usage_step = postgresql.ENUM("rewrite", "retrieve", "generate", name="usage_step")

    # documents：保存上传文件元数据和解析进度。
    # created_at 使用带时区时间；status + created_at 组合索引支持按处理状态倒序扫描。
    op.create_table(
        "documents",
        sa.Column("id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("filename", sa.String(length=512), nullable=False),
        sa.Column(
            "status",
            document_status,
            server_default="uploaded",
            nullable=False,
        ),
        sa.Column("file_type", sa.String(length=100), nullable=False),
        sa.Column("file_size", sa.BigInteger(), nullable=False),
        sa.Column("chunk_count", sa.Integer(), server_default="0", nullable=False),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.CheckConstraint(
            "chunk_count >= 0",
            name="ck_documents_chunk_count_non_negative",
        ),
        sa.CheckConstraint(
            "file_size >= 0",
            name="ck_documents_file_size_non_negative",
        ),
        sa.PrimaryKeyConstraint("id", name="pk_documents"),
    )
    op.create_index(
        "ix_documents_status_created_at",
        "documents",
        ["status", "created_at"],
        unique=False,
    )

    # chunks：保存有序切片、页码、标题路径和 1024 维向量。
    # document_id + chunk_index 唯一，保证重试解析时同一文档切片顺序稳定。
    # parent_chunk_id 自引用为两级切片预留父子关系，删除父级时级联清理子片段。
    # HNSW 与 vector_cosine_ops 用于余弦相似度近邻检索，m/ef_construction 平衡召回率与写入成本。
    # heading_path 使用 varchar[] 并建立 GIN 索引，支持按章节路径过滤且保留层级顺序。
    op.create_table(
        "chunks",
        sa.Column("id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("document_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("content", sa.Text(), nullable=False),
        sa.Column("chunk_index", sa.Integer(), nullable=False),
        sa.Column("page_number", sa.Integer(), nullable=True),
        sa.Column(
            "heading_path",
            postgresql.ARRAY(sa.String(length=255)),
            server_default=sa.text("'{}'::varchar[]"),
            nullable=False,
        ),
        sa.Column(
            "parent_chunk_id",
            postgresql.UUID(as_uuid=True),
            nullable=True,
        ),
        sa.Column("embedding", Vector(dim=1024), nullable=False),
        sa.CheckConstraint(
            "chunk_index >= 0",
            name="ck_chunks_index_non_negative",
        ),
        sa.CheckConstraint(
            "page_number IS NULL OR page_number > 0",
            name="ck_chunks_page_number_positive",
        ),
        sa.ForeignKeyConstraint(
            ["document_id"],
            ["documents.id"],
            name="fk_chunks_document_id_documents",
            ondelete="CASCADE",
        ),
        sa.ForeignKeyConstraint(
            ["parent_chunk_id"],
            ["chunks.id"],
            name="fk_chunks_parent_chunk_id_chunks",
            ondelete="CASCADE",
        ),
        sa.PrimaryKeyConstraint("id", name="pk_chunks"),
        sa.UniqueConstraint(
            "document_id",
            "chunk_index",
            name="uq_chunks_document_index",
        ),
    )
    op.create_index(
        "ix_chunks_document_index",
        "chunks",
        ["document_id", "chunk_index"],
        unique=False,
    )
    op.create_index(
        "ix_chunks_parent_chunk_id",
        "chunks",
        ["parent_chunk_id"],
        unique=False,
    )
    op.create_index(
        "ix_chunks_heading_path_gin",
        "chunks",
        ["heading_path"],
        unique=False,
        postgresql_using="gin",
    )
    op.create_index(
        "ix_chunks_embedding_hnsw",
        "chunks",
        ["embedding"],
        unique=False,
        postgresql_using="hnsw",
        postgresql_ops={"embedding": "vector_cosine_ops"},
        postgresql_with={"m": 16, "ef_construction": 64},
    )

    # conversations：多会话列表；updated_at 索引支持最近会话优先的分页。
    op.create_table(
        "conversations",
        sa.Column("id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("title", sa.String(length=255), nullable=False),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.PrimaryKeyConstraint("id", name="pk_conversations"),
    )
    op.create_index(
        "ix_conversations_updated_at",
        "conversations",
        ["updated_at"],
        unique=False,
    )

    # messages：保存用户问题和助手回答；citations 使用 JSONB 保存引用片段、页码和评分。
    # conversation_id + created_at 组合索引支持按会话顺序读取完整对话历史。
    op.create_table(
        "messages",
        sa.Column("id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("conversation_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("role", message_role, nullable=False),
        sa.Column("content", sa.Text(), nullable=False),
        sa.Column("citations", postgresql.JSONB(astext_type=sa.Text()), nullable=True),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.ForeignKeyConstraint(
            ["conversation_id"],
            ["conversations.id"],
            name="fk_messages_conversation_id_conversations",
            ondelete="CASCADE",
        ),
        sa.PrimaryKeyConstraint("id", name="pk_messages"),
    )
    op.create_index(
        "ix_messages_conversation_created_at",
        "messages",
        ["conversation_id", "created_at"],
        unique=False,
    )

    # usage_records：记录每次 rewrite/retrieve/generate 调用的 token 与延迟。
    # trace_id 支持按请求追踪链路；step + created_at 支持步骤成本趋势。
    # model + created_at 支持按模型对比调用量与延迟。
    op.create_table(
        "usage_records",
        sa.Column("id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("trace_id", sa.String(length=64), nullable=False),
        sa.Column("step", usage_step, nullable=False),
        sa.Column("model", sa.String(length=255), nullable=False),
        sa.Column("input_tokens", sa.BigInteger(), server_default="0", nullable=False),
        sa.Column("output_tokens", sa.BigInteger(), server_default="0", nullable=False),
        sa.Column("latency_ms", sa.BigInteger(), nullable=False),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.CheckConstraint(
            "input_tokens >= 0",
            name="ck_usage_input_tokens_non_negative",
        ),
        sa.CheckConstraint(
            "latency_ms >= 0",
            name="ck_usage_latency_non_negative",
        ),
        sa.CheckConstraint(
            "output_tokens >= 0",
            name="ck_usage_output_tokens_non_negative",
        ),
        sa.PrimaryKeyConstraint("id", name="pk_usage_records"),
    )
    op.create_index(
        "ix_usage_records_trace_id",
        "usage_records",
        ["trace_id"],
        unique=False,
    )
    op.create_index(
        "ix_usage_records_step_created_at",
        "usage_records",
        ["step", "created_at"],
        unique=False,
    )
    op.create_index(
        "ix_usage_records_model_created_at",
        "usage_records",
        ["model", "created_at"],
        unique=False,
    )


def downgrade() -> None:
    # 先删依赖表和枚举，再清理主表；vector 扩展保留给同库其他向量数据。
    op.drop_table("usage_records")
    op.drop_table("messages")
    op.drop_table("conversations")
    op.drop_table("chunks")
    op.drop_table("documents")

    usage_step = postgresql.ENUM(name="usage_step")
    message_role = postgresql.ENUM(name="message_role")
    document_status = postgresql.ENUM(name="document_status")
    usage_step.drop(op.get_bind(), checkfirst=True)
    message_role.drop(op.get_bind(), checkfirst=True)
    document_status.drop(op.get_bind(), checkfirst=True)
