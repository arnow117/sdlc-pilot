# sdlc-pilot — 蒸馏源地图（Distillation Source Map）

> Date: 2026-06-04 · 连接 spec → writing-plans 的"Research & Reuse"工件
> 产出方式：8 个并行 agent 各深读一组源 skill 的**完整** SKILL.md + references（非摘录），
> 覆盖 ~40 个源。本文是综合判定，不是原始转录。

## 0. 跨切面结论（先看这个）

**"我们是不是在重造 gsd？" —— 不是。** 每个 sdlc 目标的"补什么"都被两类东西主导：
(a) **剥离运行时**（把方法论从依赖里拆出来），(b) **我们的三条差异化**（路由/surface-map、可移植、拥有权）。
方法论几乎全可蒸馏；要自建的恰好是 gsd 给不了的那三件 + 几个所有源都没有的硬缺口。

| 跨切面事实 | 含义 |
|---|---|
| **每个 gstack 源带 ~700 行相同 runtime preamble**（telemetry/gbrain/artifacts-sync/AskUserQuestion 调参/gstack 二进制） | 纯噪声，蒸馏时**整段丢弃** |
| **GSD 源都依赖** `gsd-tools.cjs` / Task 子代理 / `.planning/` 目录 / AskUserQuestion | 蒸馏成**纯文件 playbook + git**；这是可移植的主要工作量 |
| **两个现成的可移植范式**：gsd 的 `text_mode`（AskUserQuestion→纯文本编号列表）+ gsd-map 的 `Task-or-sequential` 降级（探测有无 Task，没有就串行） | **直接复用到所有 skill**，这是"Codex 能跑"的标准答案 |
| **最高产、最低噪的源**：`~/.claude/skills/gstack/review/specialists/*.md` + GSD 的 agent/`.md` + ECC 纯 checklist | 角色卡 & review 维度优先取这些 |
| **App 移动 E2E：零素材、零工具**（环境无对应 MCP） | 最大净新建缺口（你有移动端需求 → 必须自建工具选型） |
| **没有任何源有"数字化覆盖率门控"** | correctness 模式的覆盖率阈值要自建 |
| **没有任何源有"eval 标准前置"** | spec 阶段为 AI 工作定 rubric 要自建 |

---

## 1. 各目标蒸馏映射

### sdlc-onboard — 覆盖：中-强
| 维度 | 内容 |
|---|---|
| **Canonical** | `gsd-map-codebase`（4-focus 并行 mapper + **Task-or-sequential 降级** + secret 双层防护 + 下游契约：哪段给哪个阶段消费） |
| **取什么** | 4 个正交 focus（stack/arch/conventions/concerns）作 PROFILE 骨架；Task-or-sequential 降级范式（移植核心）；`arch-aifriendly-doctor` 的**纯 bash 采证清单**（Codex 友好，移植性反超 gsd node 工具）+ **P13 domain-aware check（git diff→只跑该域）+ P23 模块 scoped 命令** = surface-map 机制原型；`explorer-repo-report` 的 type-detection + P0/P1/P2 探索优先级；`startup-claude-md-init` 的 PROFILE schema（技术栈表带"原因"列 + 禁止事项） |
| **补什么** | **surface-map 这张表本身**（模块→glob→**默认角色**→validate 模式，无源产出）；把 mapper 逻辑蒸馏成 driver 内嵌**纯文件角色卡**（去 external agent/node/.planning 依赖）；**单一聚合 PROFILE.md**；角色/模式取值字典 |
| **重叠** | gsd-map vs arch-doctor → gsd-map 主、arch-doctor 补"bash 采证 + scoped 命令"。`explorer-repo-compare` 对 onboard **基本全冗余**（双项目对比），不作源 |

### sdlc-spec — 覆盖：强
| 维度 | 内容 |
|---|---|
| **Canonical** | `superpowers:brainstorming`（HARD-GATE 批准前不写码 + 一次一问 + 分节获批 + 2-3 方案 + spec 自检 + 双 gate） |
| **取什么** | brainstorming 整套骨架；`hp-feature-dev` 的**文档选择矩阵**（变更类型→ADR/Spec/更新/不写）+ ADR"退化/保留"模板 + "怎么算 done 前置"；`gsd-discuss-phase` 的 gray-area 具体化（禁泛标签）+ founder/builder 角色边界 + scope guardrail/Deferred + **canonical_refs 强制累积** + **自喂循环防护**；`gsd-research-phase` 的 unknown-unknowns + Don't-Hand-Roll + confidence 分级；`gsd-plant-seed` 的结构化 deferral（Why+Trigger+Breadcrumbs） |
| **补什么** | **eval 标准前置（最大缺口，五源全无）**：AI 工作在 spec 阶段定 rubric/数据集/指标/判据；可移植（剥 Task reviewer / visual-companion / gsd-tools）；统一 spec 文档格式（收编五套异构产物） |
| **重叠** | 三处"探索"（hp 本地现状 / discuss 决策 scout / research 外部深研）→ 合成"本地三现状→轻量 scout→有界外部研究(可选)"的分级 Explore |

### sdlc-plan — 覆盖：强
| 维度 | 内容 |
|---|---|
| **Canonical** | 阶段划分=`gsd-new-project` 五准则（派生 phase/1 需求↔1 phase/2-5 可观察成功标准/100% 覆盖/traceability）；任务模板=`gsd-plan-phase` **Anti-Shallow 三字段**（read_first / acceptance_criteria 必可验 / action 含具体值） |
| **取什么** | 依赖+波次 `depends_on`+`wave`（gsd-plan-phase 唯一源）；目标倒推 must_haves；Source Audit + Coverage Gate 双向追溯；`writing-plans` 的 TDD 五步粒度 + No-Placeholder 红线 + 自查三扫 + Plan Header；`planner-breakdown-sdlc` 的 **L1-L4 复杂度分级→粒度自适应** + "每个拆分附理由" + 反过度规划 |
| **补什么** | 去运行时化（gsd-tools/Task/config/AskUserQuestion→纯文件 checklist）；统一输入=已批准 spec（裁掉 questioning）；**单技能内"spec→阶段(含依赖)→任务(含三字段)"两级贯通**；gate 可移植重写（保留"检测→注入 [BLOCKING] 任务"思想） |

### sdlc-build — 覆盖：强
| 维度 | 内容 |
|---|---|
| **Canonical** | TDD=`superpowers:test-driven-development`（RED→Verify-RED→GREEN→Verify-GREEN→REFACTOR + Iron Law + 反 rationalization 表）；调试=`superpowers:systematic-debugging`（四阶段根因） |
| **取什么** | TDD 五拍状态机 + 两个强制 Verify gate；调试四阶段 + `investigate` 的**模式签名表**(race/null/state/integration/config-drift/stale-cache) + Scope Lock + blast-radius 闸 + DEBUG REPORT 模板 + 四态协议；`hp-bugfix` 的 **bug 三分类决策树**（代码 bug/spec 缺失/设计缺陷）；`subagent-driven-development` 的**两阶段评审**(spec→quality)+ 四态（**去 subagent 化**）；`gsd-execute-phase` 的 `--interactive` 串行 inline 降级形态 |
| **补什么** | 可移植测试执行抽象（语言无关 runner 发现/运行，源全是 npm/vitest）；无 subagent 纯文件单 session 执行；交互闸→非交互 STOP 协议；**TDD↔调试统一状态机**（正常 TDD ⊕ 遇 bug 切调试子循环回 RED，无源画过这张图）；去 gstack/superpowers 运行时 |

### sdlc-validate / correctness 模式 — 覆盖：强
| 维度 | 内容 |
|---|---|
| **Canonical** | 完成前纪律=`verification-before-completion`（Iron Law + Gate Function + 反合理化表）+ `verify`（验证手段优先级阶梯：tests→typecheck/build→narrow→manual） |
| **取什么** | verify 四级阶梯作顶层流程（零依赖、Codex 能跑）；`gsd-add-tests` 的 **TDD/E2E/Skip 三分类判据 + No-skip 铁律 + Text-mode 降级**；`qa` 的 framework bootstrap + runtime→框架表 + **回归测试三步**（追 codepath/前置条件/attribution）+ baseline 健康分对比；`gsd-validate-phase` 的 **requirement-completeness 三态**（COVERED 必须 runs-green）+ "填测试不许改实现，bug 要 escalate" |
| **补什么** | **数字化覆盖率门控**（行/分支 ≥X% 否则 fail，无源有）；非 web/非 phase 通用入口；运行时解耦（qa 前 ~810 行 gstack 基建剥离）；非浏览器"真跑应用"手法（CLI/server/库 smoke）；统一证据 schema |

### sdlc-validate / e2e 模式 — 覆盖：Web 强 / OpenAPI 中 / App 弱
| 维度 | 内容 |
|---|---|
| **Canonical** | 浏览器底座=**Playwright MCP（环境已确认可用，非 browse 二进制）**；执行→失败修→截图报告闭环=`design-review` fix loop（8a-8f + risk 熔断 + before/target/after 三联截图）；证据规范=`devex-review`（Evidence+Method=TESTED/PARTIAL/INFERRED + Scope Declaration 能测/不能测自声明） |
| **取什么** | `browse` 的命令语义（snapshot-diff / ref 寻址 / annotated screenshot / responsive / chain 批处理）→ 蒸馏为 Playwright MCP 调用 playbook；design-review fix loop + diff-aware scope（file→route）；`web-api-reverse-engineering` 的 Playwright 抓包脚本 + 协议/认证识别表 + **e2e 只读安全约束** + health-check CI（OpenAPI 模态素材） |
| **补什么** | **App 移动模态（零素材零工具=最大缺口）**；用户旅程启发式推导（读路由/OpenAPI paths/PRD/diff）；多模态统一编排（选 scope→推旅程→分派 Web/API/App→汇总）；OpenAPI **正向**用例生成器（源是逆向方向）；fix loop 从"设计 finding"扩到"功能用例失败"的源码定位 |
| **工具** | 已验证 `mcp__plugin_playwright_playwright__browser_*`（navigate/click/fill_form/snapshot/take_screenshot/network_requests/console_messages/wait_for）；`network_requests` 可顺带为 OpenAPI 模态抓真实端点；`zai-mcp-server`（ui_diff_check/diagnose_error_screenshot）增强视觉断言。**App：无任何工具** |

### sdlc-validate / eval-bench 模式 — 覆盖：强
| 维度 | 内容 |
|---|---|
| **Canonical** | 方法论/词汇表=`ai-evals.md`（via gsd-ai-integration-phase）；评分骨架=`gsd-eval-review`（三态×加权×阈值 verdict + text_mode 降级） |
| **取什么** | ai-evals.md 几乎整篇：三测量法（code 优先→LLM judge→human）+ 10 预部署维度 + **rubric 1/3/5 模板** + reference dataset 准则（10-20 样本起）+ judge 必先对人类校准 + guardrail/flywheel 二分；gsd-eval-review 的 EVAL-REVIEW 模板 + 加权阈值 verdict；`benchmark` 的 **baseline-diff-threshold 双阈值**回归闭环；`benchmark-models` 的多对象同输入 + LLM judge 0-10 + baseline JSON + dry-run 预检；`tb-run-analyzer` 的**有效性甄别**(被测失败 vs 环境失败) + reward-as-authority；`tb-task-operator` 的 **oracle/nop 自检门**(先验证评估装置没坏) + pass@k 有效口径 + 条件一致性 |
| **补什么** | 真正"对 dataset 按 rubric 跑出实际质量分"的执行层（缝 ai-evals rubric × judge × verdict）；纯文件 Codex 可跑（剥所有依赖）；**spec→validate 契约接口**（读 rubric/数据集/阈值位置）；非网页性能采集 |

### sdlc-review — 覆盖：强
| 维度 | 内容 |
|---|---|
| **Canonical** | `review`（gstack /review）：scope-drift + **plan-completion 审计**（验证模式分类 DIFF-VERIFIABLE/CROSS-REPO/EXTERNAL-STATE/CONTENT-SHAPE × 状态 DONE/PARTIAL/NOT-DONE/UNVERIFIABLE + 诚实规则）+ **confidence 校准表(1-10)** + fix-first + 多专家并行 + 对抗 pass |
| **取什么** | review 整套方法论；`gsd-code-review` 的 **深度分层**(quick/standard/deep) + **per-language pitfall 表** + REVIEW.md schema；安全=`security-review` 10 域 FAIL/PASS + `gsd-secure-phase` 的 **verify-mitigation-exists（非盲扫）+ disposition(mitigate/accept/transfer) + open=0 硬门**；`plan-eng-review` 的 **15 资深工程认知模式** + test-coverage tracing + scope-challenge 阈值；`codex` 的对抗外脑角色 + prompt-injection 加固（**可选**，sdlc 在 Codex 下跑时调 codex 是循环/冗余） |
| **补什么** | 非交互/headless 变体（源都假设 AskUserQuestion）；stack-agnostic 化；去所有 runtime deps；统一 severity+confidence 模型（源混用 P0-P3 / Critical-Warning-Info / 1-10） |

---

## 2. 角色卡（roles/）素材覆盖

| 角色 | 覆盖 | 主源 / 缺口 |
|---|---|---|
| **server-dev** | 强 | `gsd-code-reviewer` 语言表(Python/Go/C/Shell pitfalls)+ `review/specialists/`(performance N+1/index、api-contract、security IDOR/injection)+ security-review 10 域。**最佳支撑** |
| **qa** | 强 | `plan-eng-review` §3 test-coverage tracing（逐 codepath + ★ 质量 rubric + E2E/EVAL/unit 决策矩阵 + 铁律回归）+ `review/specialists/testing.md`（缺负路径/隔离违规/flaky 模式）+ red-team 敌意测试心态 |
| **client-dev** | 中-强 | `flutter-dart-code-review`(语言 pitfalls 卡范式)+ JS/TS 表 + perf frontend(bundle/re-render/waterfall)+ design-checklist + 你的 `web/` 规则。**原生移动切片偏薄，需补** |
| **design** | 中 | `design-checklist.md`(AI-slop 检测 + 排版 + 交互态 + a11y)+ 你的 `web/design-quality.md`。**仅视觉前端，UX-flow/交互/产品设计深度需自建** |
| **big-data** | 弱·缺口 | **无源**。仅 `review/specialists/data-migration.md` 能种 schema-safety 子节；pipelines/数据倾斜/列存格式/lineage/幂等/数仓建模/大规模回填**全自建** |

> 高产源提示：`~/.claude/skills/gstack/review/specialists/*.md` 是角色卡最高产、最低噪的单一来源。

---

## 3. 净新建缺口登记（所有源都没有 = 我们的真活）

1. **surface-map + 改动代码路由**（模块→glob→角色→validate 模式）—— sdlc-pilot 的核心差异化，无源。
2. **eval 标准前置**（spec 阶段为 AI 工作定 rubric/数据集/阈值）。
3. **数字化覆盖率门控**（行/分支阈值）。
4. **App 移动 E2E 模态**（零素材零工具，需选型 Appium/Maestro 并实测）。
5. **用户旅程启发式推导**（多源最多到 design-review 的 file→route 粗映射）。
6. **big-data 角色卡**（几乎从零）。
7. **语言无关的测试执行抽象**（发现/运行 runner、跑单测/全量/覆盖率）。
8. **统一 schema**：PROFILE / STATE / 各阶段证据报告 / severity+confidence。
9. **可移植层**：把所有 gsd-tools/Task/gstack 二进制依赖降级为纯文件 + git + `text_mode` + `Task-or-sequential`。

---

## 4. 对 spec 的修正（agent 实读发现）

| 修正 | 详情 |
|---|---|
| `planner-breakdown-sdlc` **非空** | spec §12 写"空的、被吸收"——实际有 6.4KB 完整正文（L1-L4 复杂度分级）。仍可被 `sdlc-plan` 吸收,但要**取其 L1-L4 分级**,不是当空壳删 |
| `browse` → **Playwright MCP** | e2e Web 底座 canonical 改为环境已装的 Playwright MCP,不依赖需编译的 gstack browse 二进制（更可移植） |
| `code-review` 名称解析 | 裸名 `code-review` 在 ECC 解析到 `flutter-dart-code-review`；真正的 review 引擎是 gstack `review` —— sdlc-review 主源认 `review` |

---

## 5. Canonical 源速查

| sdlc 目标 | 第一 canonical 源 |
|---|---|
| onboard | gsd-map-codebase（+ arch-aifriendly-doctor 补 bash/scoped 命令） |
| spec | superpowers:brainstorming（+ hp-feature-dev 文档矩阵） |
| plan | gsd-new-project 五准则 + gsd-plan-phase 三字段/wave |
| build | superpowers:test-driven-development + systematic-debugging |
| validate/correctness | verification-before-completion + verify 阶梯 |
| validate/e2e | Playwright MCP + design-review fix loop |
| validate/eval-bench | ai-evals.md + gsd-eval-review |
| review | gstack review |
| roles | gstack review/specialists/*.md |
