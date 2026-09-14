# DocMind

企业级 RAG 知识库问答系统。当前包含前后端脚手架、LLM 网关、数据库迁移、文档解析/切片
与 Celery ingestion 流程；问答与检索业务尚待接入。

## 技术栈

- 前端：Vue 3.5、TypeScript 5.8、Vite 5.4、Pinia 3、Element Plus 2.11。
- 后端：Python 3.11、FastAPI、SQLAlchemy 2.0、PostgreSQL 16 + pgvector、Redis、uv。
- 质量工具：ruff、mypy、pytest、ESLint、Prettier、Vitest。
- 本地基础设施：Docker Compose。

## 目录

```text
.
├── backend/            # FastAPI 应用、测试与 uv 配置
├── frontend/           # Vue 3 应用、测试与 Vite 配置
├── scripts/            # Windows 一键启动和验证脚本
└── docker-compose.yml  # PostgreSQL + pgvector、Redis
```

## 前置条件

- Docker Desktop，且 `docker compose` 可用。
- `uv` 0.12+。
- Node.js 18.0+ 与 npm 8+。
- Python 3.11（也可由 uv 自动管理）。

## 一键启动

首次运行会在缺少 `.env` 时从对应 `.env.example` 创建本地配置：

```powershell
.\scripts\dev.ps1
```

脚本会启动 PostgreSQL 与 Redis、执行 Alembic 迁移、同步依赖，并在前台运行 API、
Celery worker 与前端开发服务：

- 前端：<http://127.0.0.1:15173>
- 后端健康检查：<http://127.0.0.1:18000/health>
- 文档上传：`POST http://127.0.0.1:18000/api/v1/documents`
- 状态轮询：`GET http://127.0.0.1:18000/api/v1/documents/{document_id}/status`
- Celery worker：消费文档解析任务
- PostgreSQL：`127.0.0.1:15432`
- Redis：`127.0.0.1:16379`

按 `Ctrl+C` 结束 API、worker 与前端进程；基础设施可用 `docker compose down` 停止。

## 一键验证

```powershell
.\scripts\verify.ps1
```

该脚本会：

1. 校验 Compose 配置、启动并等待 PostgreSQL/Redis 健康。
2. 运行后端 ruff、mypy、pytest。
3. 运行前端 Prettier、ESLint、Vitest 和 Vite 生产构建。

## 环境变量

- 根目录 `.env`：Compose 的 PostgreSQL/Redis 参数。
- `backend/.env`：FastAPI 数据库与 Redis 连接。
- `frontend/.env`：浏览器可见的 API 地址，不得放密钥。

仓库只提交 `.env.example`。真实密钥不得写入代码、测试或 Git 历史。
