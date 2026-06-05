# Changelog

遵循语义化版本。格式参考 Keep a Changelog。

## [0.1.0] — 2026-06-05

首个可安装版本(Claude Code 插件)。

### Added — 核心
- **主线**:`sdlc` driver + 6 流程 skill(onboard / spec / plan / build / validate / review)。
- **角色卡(6)**:qa · client-dev · server-dev · design · big-data(stub)· architect(全链路接缝)。
- **validate 模式(3)**:correctness · e2e(Web/OpenAPI/App)· eval-bench。
- **路由**:`role-routing.md` R1–R8(改动代码 → 角色 + 验证模式;含 R7 配置型工程、R8 跨链路)。
- **状态契约**:`PROFILE.md`(项目级)+ `STATE.md`(feature 级)+ `sdlc-gate` 行。

### Added — 工程/纪律
- **改动驱动路由** + **跨会话状态持久化**;**Task-or-sequential 降级**(Codex 可跑)。
- **build wave 并行执行**(同 wave 多阶段 fan-out)。
- **eval 标准前置**(spec §5)+ **设计契约前置**(spec §2.6b → `DESIGN.md`)。
- **可选发散 ideation**(`divergence-frames.md`,蒸馏 adhd)+ **范围塑造**(spec §2.4b)。
- **受评接收纪律**(`receiving-feedback.md`,防过度修复)。
- **push 前 SDLC 检查**:本地 `pre-push` hook(纯 shell,读 `sdlc-gate`)。
- 打包为插件(`.claude-plugin/`)+ `CLAUDE.md`/`AGENTS.md` 维护契约 + `scripts/validate-skills` 结构 lint。

### 蒸馏自
superpowers · gstack(+ review/specialists)· GSD(+ ai-evals.md)· agency-agents(MIT)· adhd(MIT)· 用户自有 skill(hp-* / explorer-* / startup-* / tb-* / web-api-reverse-engineering)· Playwright MCP。详见 `README.md` 溯源表 + `docs/distillation-source-map.md`。

### 已知 / 待办
- 仅 dogfood 过 onboard(测 happycompany);完整 feature 主线端到端试跑待做。
- App E2E 工具(Maestro)选型待实测;big-data 角色为 stub。
- 见设计 spec §13。
