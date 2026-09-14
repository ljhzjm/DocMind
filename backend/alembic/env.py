from __future__ import annotations

import os
from logging.config import fileConfig

import app.models  # noqa: F401  # 导入模型以填充 Base.metadata
from alembic import context
from app.core.config import get_settings
from app.db.base import Base
from sqlalchemy import engine_from_config, pool

config = context.config

if config.config_file_name is not None:
    fileConfig(config.config_file_name, disable_existing_loggers=False)

target_metadata = Base.metadata


def get_database_url() -> str:
    """按命令行/测试覆盖、环境变量、应用配置的顺序解析数据库 URL。"""
    configured_url = config.get_main_option("sqlalchemy.url")
    if configured_url:
        return configured_url

    environment_url = os.getenv("DATABASE_URL", "")
    if environment_url:
        return environment_url

    settings_url = get_settings().database_url
    if settings_url:
        return settings_url

    raise RuntimeError("DATABASE_URL is required to run Alembic migrations")


def run_migrations_offline() -> None:
    """离线模式只输出 SQL，不建立数据库连接。"""
    context.configure(
        url=get_database_url(),
        target_metadata=target_metadata,
        literal_binds=True,
        dialect_opts={"paramstyle": "named"},
        compare_type=True,
    )
    with context.begin_transaction():
        context.run_migrations()


def run_migrations_online() -> None:
    """在线模式使用短生命周期连接执行迁移。"""
    configuration = config.get_section(config.config_ini_section) or {}
    configuration["sqlalchemy.url"] = get_database_url()
    connectable = engine_from_config(
        configuration,
        prefix="sqlalchemy.",
        poolclass=pool.NullPool,
    )

    with connectable.connect() as connection:
        context.configure(
            connection=connection,
            target_metadata=target_metadata,
            compare_type=True,
        )
        with context.begin_transaction():
            context.run_migrations()


if context.is_offline_mode():
    run_migrations_offline()
else:
    run_migrations_online()
