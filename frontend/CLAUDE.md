# DocMind Frontend Engineering Rules

## 1. 技术栈与版本约束

- Node.js：18.0+；本地优先使用活跃 LTS，并以锁文件安装依赖。
- Vue：3.5.x，使用 Composition API 和 `<script setup lang="ts">`。
- TypeScript：5.8.x，启用严格类型检查。
- 构建：Vite 5.4.x；依赖与脚本以 `package.json`、`package-lock.json` 为准。
- 状态管理：Pinia 3.x，仅保存跨页面或跨组件状态。
- UI：Element Plus 2.11.x；优先复用组件与已有设计变量。
- 测试：Vitest 1.6.x + Vue Test Utils + jsdom。
- 代码质量：ESLint 8 + Prettier 3；禁止手工修改锁文件。

## 2. 目录结构与职责

```text
frontend/
├── public/               # 原样复制的静态资源
└── src/
    ├── api/              # HTTP 客户端与接口封装
    ├── assets/           # 由 Vite 处理的图片、字体等资源
    ├── components/       # 可复用且与本项目无关的展示组件
    ├── composables/      # 可复用组合式函数
    ├── layouts/          # 页面布局
    ├── router/           # 路由定义与守卫
    ├── stores/           # Pinia stores
    ├── types/            # 跨模块 TypeScript 类型
    ├── utils/            # 无状态工具函数
    ├── views/            # 路由页面
    ├── App.vue           # 应用根组件
    └── main.ts           # 应用组装入口
```

- 页面只做组合和路由级状态，业务请求放 `api/`，流程状态放 `stores/`。
- `components/` 不得直接调用模型供应商；所有请求走后端 API。
- 类型优先靠近使用处；被三个以上模块复用时再移动到 `types/`。

## 3. TypeScript 与 Vue 规范

- 禁止使用隐式 `any`；外部数据先定义类型并在 API 边界校验。
- API 响应和请求模型使用明确类型，禁止用字符串拼接构造 URL。
- 组件名使用多单词 `PascalCase`，文件名与组件名一致。
- 组件属性使用 `defineProps<T>()`，事件使用 `defineEmits<T>()`。
- 使用 `computed` 派生状态，禁止在模板中写复杂表达式或产生副作用。
- 状态变化集中在 Pinia action 或 composable，组件不得隐式修改共享对象。
- 异步请求必须处理加载、空、错误和重试状态；组件卸载时清理监听器与定时器。
- 全局样式只放设计令牌与重置样式，组件样式默认使用 `scoped`。
- 注释只解释不明显的约束或原因，不复述代码。

命名约定：

- 组件文件与类型：`PascalCase`
- 页面视图：`XxxView.vue`，路由名称使用 `kebab-case`
- composables：`useXxx`
- stores：`useXxxStore`
- 变量、函数：`camelCase`
- 常量：`UPPER_SNAKE_CASE`
- 测试：`*.spec.ts`

## 4. 测试与质量约定

- 每个行为变更必须附带可运行测试；bug 修复先补回归测试。
- 纯逻辑优先单元测试，复杂用户流程使用组件测试；必要时增加端到端测试。
- 禁止依赖真实模型供应商或生产后端；测试使用类型安全的 mock 或测试适配器。
- 最低验证命令：

```bash
npm run format:check
npm run lint
npm test
npm run build
```

- 变更界面后还需在浏览器中检查目标视口，并确认无控制台错误、文本溢出或遮挡。
- 禁止通过放宽 TypeScript、ESLint、测试断言来掩盖问题。

## 5. 禁止事项

1. 禁止在前端硬编码 OpenAI、DeepSeek、Qwen、Anthropic 等供应商 SDK、URL 或协议。
   所有模型调用必须经后端 `app/llm/` 网关层提供的 API。
2. 禁止把 API Key、密码、令牌写进代码、测试、文档或提交到 Git。真实配置只放
   本机 `.env`；仓库只提交 `.env.example`，其中不得含真实凭据。
3. 每次改动必须附带可运行的测试。无法自动化的场景必须提供可复现的手工验证步骤，
   并在交付说明中写明。
4. 单次生成超过 300 行代码或文档时，必须先停止并请用户 review；获得确认后再继续。
