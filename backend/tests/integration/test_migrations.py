from pathlib import Path
from uuid import uuid4

import psycopg
import pytest
from alembic import command
from alembic.config import Config
from app.core.config import get_settings
from psycopg import sql
from sqlalchemy import create_engine, inspect, text
from sqlalchemy.engine import make_url

pytestmark = pytest.mark.integration

BACKEND_ROOT = Path(__file__).resolve().parents[2]
DEFAULT_DATABASE_URL = "postgresql+psycopg://docmind:docmind_local@127.0.0.1:15432/docmind"


def configured_database_url() -> str:
    """优先使用应用配置，缺失时回退到 Docker Compose 的本地开发库。"""
    return get_settings().database_url or DEFAULT_DATABASE_URL


def test_initial_migration_upgrade_and_downgrade(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    source_url = make_url(configured_database_url())
    database_name = f"docmind_test_{uuid4().hex}"
    admin_url = source_url.set(database="postgres")
    test_url = source_url.set(database=database_name)
    migration_dsn = test_url.render_as_string(hide_password=False)
    monkeypatch.setenv("DATABASE_URL", migration_dsn)
    admin_dsn = admin_url.set(drivername="postgresql").render_as_string(hide_password=False)

    with psycopg.connect(admin_dsn, autocommit=True) as admin_connection:
        admin_connection.execute(
            sql.SQL("CREATE DATABASE {}").format(sql.Identifier(database_name))
        )

    engine = create_engine(test_url)
    try:
        config = Config(str(BACKEND_ROOT / "alembic.ini"))
        command.upgrade(config, "head")

        inspector = inspect(engine)
        assert {
            "alembic_version",
            "documents",
            "chunks",
            "eval_dataset",
            "chunk_terms",
            "conversations",
            "messages",
            "usage_records",
        }.issubset(inspector.get_table_names())

        with engine.connect() as connection:
            vector_type = connection.scalar(
                text(
                    """
                    SELECT format_type(attribute.atttypid, attribute.atttypmod)
                    FROM pg_attribute AS attribute
                    JOIN pg_class AS relation ON relation.oid = attribute.attrelid
                    WHERE relation.relname = 'chunks'
                      AND attribute.attname = 'embedding'
                    """
                )
            )
            hnsw_definition = connection.scalar(
                text(
                    """
                    SELECT indexdef
                    FROM pg_indexes
                    WHERE schemaname = 'public'
                      AND indexname = 'ix_chunks_embedding_hnsw'
                    """
                )
            )
            embedding_is_nullable = connection.scalar(
                text(
                    """
                    SELECT is_nullable
                    FROM information_schema.columns
                    WHERE table_name = 'chunks'
                      AND column_name = 'embedding'
                    """
                )
            )
            usage_steps = connection.scalars(
                text(
                    """
                    SELECT enumlabel
                    FROM pg_enum
                    JOIN pg_type ON pg_type.oid = pg_enum.enumtypid
                    WHERE pg_type.typname = 'usage_step'
                    ORDER BY enumsortorder
                    """
                )
            ).all()
            document_statuses = connection.scalars(
                text(
                    """
                    SELECT enumlabel
                    FROM pg_enum
                    JOIN pg_type ON pg_type.oid = pg_enum.enumtypid
                    WHERE pg_type.typname = 'document_status'
                    ORDER BY enumsortorder
                    """
                )
            ).all()

        assert vector_type == "vector(1024)"
        assert embedding_is_nullable == "YES"
        assert hnsw_definition is not None
        assert "USING hnsw" in hnsw_definition
        assert "vector_cosine_ops" in hnsw_definition
        assert document_statuses == ["uploaded", "parsing", "ready", "failed"]
        assert usage_steps == ["rewrite", "retrieve", "rerank", "generate"]

        command.downgrade(config, "base")
        assert "documents" not in inspect(engine).get_table_names()
    finally:
        engine.dispose()
        with psycopg.connect(admin_dsn, autocommit=True) as admin_connection:
            admin_connection.execute(
                sql.SQL("DROP DATABASE IF EXISTS {} WITH (FORCE)").format(
                    sql.Identifier(database_name)
                )
            )
