# Changelog

遵循语义化版本。格式参考 Keep a Changelog。

## [0.2.1] — 2026-06-05

流程 skill 去"命令手册化":skill 是**约束 + 原则**,不是 bash cookbook。

### Changed
- **onboard Phase A 重写**:~70 行脆弱 bash(`find`/`grep`/`awk` 一行流,带 zsh-glob/wc-total/嵌套清单/噪声等坑)→ ~20 行「采什么(4 视角表)+ 避坑原则」。之前 dogfood 找出的"缺陷"多是规定命令自身的 bug,原则化后消失。
- **去 cookbook**:onboard/driver 空仓判定、plan spec-获批检查、review base 分支探测链、各入口 `ls -la`/`ls` 检查 → 全改为原则/要确认的事。
- **保留**:`git diff --name-only` 三连(稳定且是路由契约输入)、`scripts/sdlc-guard` 调用(确定性强门禁)、`references/languages/*`·`deploy-targets/*`(参考卡,具体命令即交付物)。
- **CLAUDE.md 加铁律 #4**:skill 约束"做什么/为什么/避哪些坑",不规定"怎么执行命令";附"流程 vs 环境工具调用"判据,防蒸馏退回命令手册。

### Fixed
- **README 安装章节**:方式二软链循环漏了 `sdlc-ship`(枚举技能名易漏)→ 改为遍历 `skills/*/`,永不漏新增技能;路径去硬编码,适配"全新克隆"场景 + 加自检。

## [0.2.0] — 2026-06-05

build 后的能力扩张(角色 7、流程 skill 7、+ 语言包 / 部署)。

### Added
- **architect 角色**(全链路数据结构/契约对齐,routing R8 跨 ≥2 面触发)。
- **ai-readiness 角色**(面向 AI 友好度/可维护性,蒸 arch-doctor 10 维+23 模式;onboard 只读体检 → PROFILE;routing R9)。整改走 feature loop,不另起 skill。
- **doubt-driven 对抗性自我证伪**(spec §2.5,架构/数据/契约决策前)+ **ADR 模板正式化**(spec §2.7)。
- **设计契约前置**(spec §2.6b → DESIGN.md)。
- **7 语言包**(`references/languages/`:Python/TS/Go/Rust/Kotlin/Swift/Java-Spring,陷阱+测试+lint+LSP+框架,命令实测;routing §7;角色卡/validate/ai-readiness 接入)。
- **work-type 流程画像**(STATE:feature/remediation/hotfix,偏置 granularity 不取消硬门)+ `/sdlc next`。
- **并发/边界硬门**(`scripts/sdlc-guard` + `pre-commit` hook,git 执行模型绕不过;STATE branch/worktree 戳;多特性并行引导 worktree)。
- **retro→distillation**(从走过完整 loop 的 session 提炼,门控)。
- **★sdlc-ship 部署阶段**(第 7 流程 skill,`review→verify→ship`):环境晋级流水线 dev→staging→canary→full,每段 deploy→smoke→门→晋级/回滚;**适配多目标**(`references/deploy-targets/{static-site,container,vps}.md`)+ 通用方法论(`deployment-patterns.md`);项目特定配置从目标工程 PROFILE.Deploy/CLAUDE.md 抽,不预置;密钥不入仓。onboard 加只读部署探测。

### 蒸馏新增源
arch-aifriendly-doctor · adhd · doubt-driven-development · plan-ceo-review · session-miner/retro/orchestrator-flow-reflect · ECC 全语言包(python/go/rust/kotlin/swift/java-spring testing+security)· rust-*/swift-* 用户技能 · deployment-patterns/land-and-deploy/setup-deploy/gsd-ship/publish-research-site。

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
- **并发/边界硬门禁**:`scripts/sdlc-guard`(确定性检测 STATE 与 branch/worktree 串台)+ `pre-commit` hook(git 执行、模型绕不过);STATE 加 `branch`/`worktree` 戳;driver 入口软层 + onboard 询问安装;引导用 worktree 做多特性隔离。
- 打包为插件(`.claude-plugin/`)+ `CLAUDE.md`/`AGENTS.md` 维护契约 + `scripts/validate-skills` 结构 lint。

### 蒸馏自
superpowers · gstack(+ review/specialists)· GSD(+ ai-evals.md)· agency-agents(MIT)· adhd(MIT)· 用户自有 skill(hp-* / explorer-* / startup-* / tb-* / web-api-reverse-engineering)· Playwright MCP。详见 `README.md` 溯源表 + `docs/distillation-source-map.md`。

### 已知 / 待办
- 仅 dogfood 过 onboard(测 agentic-config-demo);完整 feature 主线端到端试跑待做。
- App E2E 工具(Maestro)选型待实测;big-data 角色为 stub。
- 见设计 spec §13。
