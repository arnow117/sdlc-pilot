<!--
  PROFILE.md — 项目级长命记忆模板（sdlc-pilot）
  ─────────────────────────────────────────────────────────
  作用：项目的"它是什么"长期画像。落在【目标仓库】的
        `<target-repo>/.sdlc/PROFILE.md`，不在 skill 里。
  生命周期：长命。由 sdlc-onboard 建一次，被之后每个 feature 读取共享；
            仅在架构漂移时刷新（见下文 driver 的漂移检测）。
  与 STATE.md 的区别：
    - PROFILE.md = 项目级、长命、所有 feature 共享（本文件）。
    - STATE.md   = feature 级、短命、单任务 handoff。
  核心职责：承载【架构 surface map】——路由决策函数的可追踪输入（spec §6.1）。
    决策 = resolve(git diff × PROFILE.surface-map × role-routing 规则)。
    其中 surface-map 是慢变、被追踪的输入；diff 是每次重算的临时输入。
  漂移检测：driver 在 session 开始时拿 diff 路径对照本 surface map；
            若变更触及 map 里没有的模块/面（如全新服务、首个移动端目录），
            提示"架构已漂移——刷新 PROFILE？"并可重跑 sdlc-onboard 相关部分。
  使用方式：
    1) 复制本模板到 <target-repo>/.sdlc/PROFILE.md
    2) 删除本注释块与所有 <填写...> 占位
    3) 由 sdlc-onboard 据实填写；后续 feature 只读，不改（除非刷新）
  ─────────────────────────────────────────────────────────
-->

# Project Profile: <项目名>

<!--
  顶部元数据：技术栈用列表；带"原因"列的展开形式见下方 ## Tech stack 表。
  test-commands 是语言无关的命令抽象，validate/correctness 据此发现并运行套件。
  v1 语言范围 = Python + Web(TS)；命令示例对应 pytest/coverage + vitest/playwright/tsc。
-->

tech-stack: [<填写，例如：next.js, fastapi, postgres>]
test-commands: { unit: "<例如 pytest>", coverage: "<例如 pytest --cov>", e2e: "<例如 playwright test>", typecheck: "<例如 tsc --noEmit>", build: "<例如 pnpm build>" }

## Tech stack

<!--
  技术栈明细表，带"原因"列（为何选它）——帮助后续 feature 理解约束与取舍。
  source: startup-claude-md-init 的 schema（技术栈表带原因 + 禁止事项）。
-->

| 层 | 技术 | 选它的原因 |
|----|------|-----------|
| <例如 前端> | <例如 Next.js> | <例如 SSR + 团队熟悉> |
| <例如 后端> | <例如 FastAPI> | <例如 异步 + 自动 OpenAPI> |
| <例如 数据> | <例如 Postgres> | <填写> |

## Surface map

<!--
  ★ 路由决策的可追踪输入（spec §4 / §6.1）。
  每个模块/面：globs（匹配的文件路径）→ 默认角色卡 → 默认 validate 模式。
  进入 build/validate/review 时，git diff 的路径对照本表 + role-routing 规则，
  动态解析出本轮活跃角色与验证模式（结果快照进 STATE.md，不在此持久化）。
  取值字典：
    roles = client-dev | server-dev | design | qa | big-data | security
    modes = correctness | e2e:Web | e2e:OpenAPI | e2e:App | eval-bench
  下面为示例行，按实际仓库结构增删改。
-->

- web-frontend:  globs[ web/**, components/** ]   roles[client-dev, design]   modes[correctness, e2e:Web]
- mobile-app:    globs[ ios/**, android/** ]      roles[client-dev, design]   modes[correctness, e2e:App]
- api:           globs[ services/api/** ]          roles[server-dev]           modes[correctness, e2e:OpenAPI]
- ai-strategy:   globs[ models/**, strategy/** ]   roles[server-dev, qa]       modes[correctness, eval-bench]
- data:          globs[ pipelines/** ]             roles[big-data]             modes[correctness]

## Conventions

<!--
  项目约定：命名、目录结构、提交规范、代码风格要点、不可变/错误处理等本仓约束。
  source: gsd-map-codebase 的 conventions focus + startup-claude-md-init 的"禁止事项"。
-->

- <填写，例如：所有 API 响应用统一 envelope（success/data/error）>
- <填写，例如：禁止就地变更，始终返回新对象>

## Entry points

<!--
  关键入口：服务启动命令、主程序文件、路由表位置、配置入口、迁移命令等。
  让全新上下文的 agent 知道"从哪开始读/从哪开始跑"。
-->

- <填写，例如：服务启动 = uvicorn services.api.main:app>
- <填写，例如：路由表 = services/api/routes.py>
- <填写，例如：前端入口 = web/app/layout.tsx>

## Known risks

<!--
  已知风险/坑点：脆弱模块、技术债、性能热点、易踩的历史问题。
  source: gsd-map-codebase 的 concerns focus + arch-aifriendly-doctor 采证。
-->

- <填写，例如：orders 模块有 N+1 查询，改动时注意>
- <填写，例如：无 e2e 覆盖的支付回调，改动需手动验证>
