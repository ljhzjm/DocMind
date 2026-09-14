# DocMind Backend Engineering Rules

## 1. 技术栈与版本约束

- Python：3.11.x。`pyproject.toml` 固定 `>=3.11,<3.12`，不要使用仅 3.12+ 可用的语法。
- 包管理：仅使用 `uv`。依赖声明写在 `pyproject.toml`，锁文件为 `uv.lock`，禁止手工编辑锁文件。
- Web：FastAPI 0.115+，Pydantic 2.x，Uvicorn。
- 数据层：SQLAlchemy 2.0 风格 API、Alembic、PostgreSQL 16 + pgvector、psycopg 3。
- 缓存与任务：Redis 6.x 客户端；不得把 Redis 当作唯一持久化存储。
- 代码质量：`ruff` 负责格式化与 lint；`mypy --strict` 负责类型检查。
- 测试：`pytest`，异步测试使用 `pytest-asyncio`。
- 版本以 `pyproject.toml` 和 `uv.lock` 为准；新增依赖必须使用 `uv add` 或 `uv add --dev`。

## 2. 目录结构与依赖方向

```text
backend/
├── app/
│   ├── api/              # HTTP 路由、依赖注入入口
│   ├── core/             # 配置、安全、日志等横切能力
│   ├── db/               # Engine、Session、迁移接入点
│   ├── llm/              # 唯一模型供应商网关层
│   ├── models/           # SQLAlchemy ORM 模型
│   ├── repositories/     # 数据库读写，不承载业务编排
│   ├── schemas/          # Pydantic 输入输出模型
│   ├── services/         # 用例编排与领域流程
│   ├── workers/          # 后台任务入口
│   └── main.py           # FastAPI 应用工厂与组装
└── tests/
    ├── unit/             # 无外部服务的快速测试
    └── integration/      # PostgreSQL、Redis 等集成测试
```

依赖方向：`api -> services -> repositories -> models/db`。`llm/` 可被
`services/` 调用，但 `api/`、`models/`、`repositories/` 不得直接调用模型供应商。

## 3. Python 代码规范

- 所有公开函数、方法和类必须有类型标注；避免无理由的 `Any`。
- 使用 `ruff format` 和 `ruff check --fix`，行长上限 100。
- 使用异步 I/O；数据库异步访问使用 SQLAlchemy 2.0 async API。
- FastAPI 依赖通过 `Depends` 注入，禁止在路由中创建全局 Session。
- 配置集中使用 Pydantic Settings，环境变量名使用大写下划线。
- 日志使用标准 `logging` 接口；禁止 `print` 和记录密钥、令牌、完整请求正文。
- 异常须转换为明确的领域或 HTTP 错误，禁止裸 `except Exception`。
- 注释只解释不明显的约束或原因，不复述代码。

命名约定：

- 模块、函数、变量：`snake_case`
- 类、异常、Pydantic 模型：`PascalCase`
- 常量：`UPPER_SNAKE_CASE`
- 私有成员：前导单下划线
- 测试文件：`test_<behavior>.py`
- 数据库表和列：`snake_case`

## 4. 测试约定

- 每个行为变更必须附带可运行测试；修 bug 先补失败用例。
- `tests/unit/` 不依赖 PostgreSQL、Redis 或网络。
- `tests/integration/` 可使用 Docker Compose 提供的基础服务，并显式标记。
- 外部模型供应商在单元测试中必须通过 `app/llm/` 接口替换，禁止在业务层打补丁。
- 最低验证命令：

```bash
uv run ruff format --check .
uv run ruff check .
uv run mypy app tests
uv run pytest
```

- 集成测试通过后，还应在实际 PostgreSQL + pgvector 上验证迁移和关键查询。
- 禁止提交通过 `skip`、降低断言或删除测试来“修复”失败。

## 5. 禁止事项

1. 禁止在 `app/llm/` 之外导入或硬编码 OpenAI、DeepSeek、Qwen、Anthropic
   等供应商 SDK。所有对话、Embedding、重排调用必须走 `app/llm/` 网关层。
2. 禁止把 API Key、密码、令牌写进代码、测试、文档或提交到 Git。真实配置只放
   本机 `.env`；仓库只提交 `.env.example`，其中不得含真实凭据。
3. 每次改动必须附带可运行的测试。无法自动化的场景必须提供可复现的手工验证步骤，
   并在交付说明中写明。
4. 单次生成超过 300 行代码或文档时，必须先停止并请用户 review；获得确认后再继续。