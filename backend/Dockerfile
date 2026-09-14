FROM ghcr.io/astral-sh/uv:python3.11-bookworm-slim

WORKDIR /app

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    UV_COMPILE_BYTECODE=1 \
    UV_LINK_MODE=copy \
    UV_NO_CACHE=1

COPY pyproject.toml uv.lock ./
RUN uv sync --frozen --no-dev

COPY alembic.ini ./
COPY alembic ./alembic
COPY app ./app
COPY docker-entrypoint.sh ./docker-entrypoint.sh
RUN chmod +x ./docker-entrypoint.sh \
    && groupadd --system --gid 10001 docmind \
    && useradd --system --uid 10001 --gid docmind --create-home docmind \
    && mkdir -p /app/storage/uploads \
    && chown -R docmind:docmind /app/storage

USER docmind

EXPOSE 8000
ENTRYPOINT ["./docker-entrypoint.sh"]
