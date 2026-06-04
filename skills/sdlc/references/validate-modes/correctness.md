---
mode: correctness
triggers: [always]   # correctness 是 validate 的默认模式，任何 diff 都跑
distilled-from:
  - verification-before-completion   # Iron Law + Gate Function + 反合理化表
  - verify                           # 验证手段优先级阶梯 tests→typecheck/build→narrow→manual
  - gsd-add-tests                    # TDD/E2E/Skip 三分类 + No-skip 铁律 + text_mode
  - qa                               # framework bootstrap + runtime→框架表 + 回归测试三步 + baseline 健康分
  - gsd-validate-phase               # requirement-completeness 三态（COVERED=runs-green）+ 不许改实现/bug escalate
self-built:
  - 数字化覆盖率门控（行/分支阈值，pytest-cov / nyc/c8，Python+TS）
  - 统一证据 schema（correctness-report）
---

# Validate 模式：correctness（正确性）

> 角色：把"应该能跑"变成"已验证能跑"的硬证据。这是 validate 中枢的默认模式，
> 任何 diff 都会触发。引擎=Claude + Read/Edit/Bash/Grep，无运行时依赖，Codex 可跑。

---

## 何时触发

- **always**：进入 `sdlc-validate` 时 correctness 永远在 active modes 里（见 role-routing）。
- 单独跑：`/sdlc validate --mode=correctness`，或 `sdlc-onboard` 拿它做 brownfield 基线健康检查（baseline）。
- 与其它模式叠加：前端改动叠 e2e，AI/策略改动叠 eval-bench；correctness 永远是底座。

---

## 关注点（这个模式在乎什么）

1. **证据，不是断言**——任何"通过/完成/修好了"必须配本轮真跑出来的命令输出。
2. **覆盖到行为，不是覆盖到文件**——测试要打中"它做了什么"，不是"它能 import / 渲染"。
3. **三态诚实**——每条需求/验收点只能是 COVERED / PARTIAL / MISSING，不许把 PARTIAL 说成 COVERED。
4. **填测试不改实现**——validate 阶段写测试暴露 bug；发现实现 bug 要 **escalate 回 build**，不在这里偷偷改实现。
5. **数字门控**——覆盖率有明确阈值，达不到就 fail，不靠感觉。

---

## 步骤流程

### Step 0 — 发现测试基建（runtime → framework）

跑探测，确定语言、框架、跑测命令。v1 只认 Python + Web(TS)，但探测保持通用。

```bash
# runtime 探测
[ -f pyproject.toml ] || [ -f requirements.txt ] && echo "RUNTIME:python"
[ -f package.json ] && echo "RUNTIME:node"
# 已有测试基建
ls pytest.ini pyproject.toml tox.ini 2>/dev/null
ls vitest.config.* jest.config.* playwright.config.* 2>/dev/null
ls -d tests/ test/ __tests__/ spec/ e2e/ 2>/dev/null
```

| runtime | 首选框架 | 跑单测 | 覆盖率 |
|---------|---------|--------|--------|
| Python  | pytest  | `pytest` | `pytest --cov=<pkg> --cov-report=term-missing` (pytest-cov) |
| Node/TS | vitest  | `vitest run` | `vitest run --coverage` (c8/istanbul) |
| Next.js | vitest + playwright | `vitest run` | `vitest run --coverage` |

- **检测到框架**：读 2-3 个现有测试文件学约定（命名、import、断言风格、setup/teardown）。**不要凭文件名臆测**，照抄约定。
- **无框架**：bootstrap（装框架→建最小 config→建目录→写 1 个真测试验证基建跑通）。bootstrap 失败就 `git checkout` 回滚相关文件，记 BLOCKED，不假装有测试。
- 把跑测命令、覆盖率命令、阈值写进/读自 `PROFILE.md` 的 `test-commands`。

### Step 1 — 列出"必须被证明的行为"

来源（按优先级）：`spec.md` 验收标准 → `plan.md` 任务的 acceptance_criteria → 本轮 `git diff` 改动的函数/分支。
每条变成一行：`{ 需求/行为, 触发条件, 期望结果 }`。这是后面三态判定的清单。

### Step 2 — 分类每个改动文件（TDD / E2E / Skip）

读文件确认，不靠文件名。

| 类别 | 判据 | 测试类型 |
|------|------|---------|
| **TDD（单测）** | 纯函数/可写 `assert fn(input)==output`：计算、定价、校验、解析、数据变换、状态机、工具函数 | 单元测试 |
| **E2E** | 需浏览器/真实交互才能验：键盘快捷键、导航路由、表单提交、选择、拖拽、弹窗、数据网格 | 交给 **e2e 模式** 处理 |
| **Skip** | 无逻辑：纯 CSS/样式、配置、胶水代码、迁移、纯 CRUD、类型/DTO | 不写 |

> E2E 类不在 correctness 里跑，路由到 e2e 模式。correctness 负责单测 + 集成 + 覆盖率 + 真跑应用。

### Step 3 — 补齐测试（填测试，不改实现）

对每条 MISSING / PARTIAL 的行为补单测/集成测试：

- **AAA 结构**：Arrange（造触发该行为的精确前置状态）→ Act（执行暴露行为的动作）→ Assert（断言**正确行为**，禁止 `toBeDefined()` / `不抛异常` 这种空断言）。
- 顺手把追溯到的相邻边界也测了（null、空数组、边界值）。
- **铁律：填测试时不许改实现文件。** 若测试暴露实现 bug：
  - 记一条 `⚠️ 实现 bug：{现象} / 期望 {x} / 实际 {y} / 文件 {path}`，
  - **escalate 回 sdlc-build**（build 内的 TDD↔调试子循环修），correctness 这一轮该需求标 PARTIAL。
  - 单条 bug 调试 ≤ 3 次迭代仍无解 → escalate，不死磕。

### Step 4 — 真跑：单测 → typecheck/build → narrow → manual（验证阶梯）

按这个**优先级阶梯**取证（来自 verify），上层够用就不必下探：

```
1. 已有测试（最可信，零成本）       → 跑全量 / 相关子集
2. Typecheck / Build（编译级）      → 注意：linter ≠ compiler，要单独跑 build
3. Narrow 直接命令检查（窄）        → 针对单个行为的最小直接验证
4. Manual / 交互验证（最后手段）    → 描述步骤 + 收集可观察证据；非浏览器场景的"真跑应用"
```

每步都**完整跑、读全输出、看 exit code、数失败数**（Gate Function，见下）。
非浏览器的"真跑应用"smoke：CLI（`--help` / 子命令 happy path）、server（起服务 + 打 health endpoint）、库（import + 调一个公共入口）。

### Step 5 — 覆盖率门控（数字化，自建）

跑覆盖率命令，对**本轮改动相关**的行/分支覆盖率与阈值比较：

| 语言 | 命令 | 默认门控 |
|------|------|---------|
| Python | `pytest --cov=<pkg> --cov-report=term-missing --cov-fail-under=<X>` | 行 ≥ 80%，关键模块分支 ≥ 70% |
| TS | `vitest run --coverage` + config `coverage.thresholds`（c8/istanbul） | lines/statements ≥ 80%，branches ≥ 70% |

门控规则（写进 PROFILE，可按项目调）：
- **新增/改动代码**的行覆盖 < 阈值 → **FAIL**，回 Step 3 补测试。
- 用 `--cov-fail-under` / `coverage.thresholds` 让工具自己以 **非零 exit code** 把关，别靠肉眼读百分比。
- 阈值是"门"不是"分"：达标即过，不刷高分；纯样式/配置/迁移文件可在 config 里排除出分母。
- 阈值缺失时：默认 行 80% / 分支 70%；happycompany dogfood 用此默认。

### Step 6 — 三态判定 + 回归保护

对 Step 1 每条行为打三态（来自 gsd-validate-phase）：

| 状态 | 判据 |
|------|------|
| **COVERED** | 有测试，打中该行为，**本轮真跑 green** |
| **PARTIAL** | 有测试但 failing / 不完整 / 被 escalate 的实现 bug 阻塞 |
| **MISSING** | 没有任何测试 |

**COVERED 必须 = runs-green。** 没真跑过的、上一次跑的、"应该会过的"一律不算 COVERED。

修过 bug 的，写**回归测试**（来自 qa 三步）：
1. 学最近的 2-3 个同类测试，照抄风格（像同一个人写的）。
2. **追 bug 的 codepath**：什么输入/状态触发？走了哪条分支？在哪行断？相邻还有哪些输入会命中同一路径？
3. 只跑这个新测试文件确认 green；带 attribution 注释（`# Regression: <id> — 什么坏了 / 发现于 <date>`）。

### Step 7 — 写证据报告

把结果写进 `.sdlc/validate/correctness-report.md`（schema 见下），更新 `STATE.md` 的 gate。

---

## 门控（exit gates，必须全过才算 correctness 通过）

- [ ] 测试基建已发现或 bootstrap 成功（否则 BLOCKED，不假装）。
- [ ] Step 1 每条行为都有三态判定，无遗漏。
- [ ] 全量/相关测试**本轮真跑**：0 failures（贴命令 + exit 0 + 通过数）。
- [ ] typecheck/build 真跑 exit 0（linter 过不算）。
- [ ] 覆盖率门控达标（工具以非零 exit 把关，不靠肉眼）。
- [ ] 无 COVERED 项是靠"应该过/上次过"判定的。
- [ ] 实现 bug 全部 escalate 回 build，未在 validate 偷改实现。
- [ ] 修过的 bug 有回归测试且单独跑 green。

任一项不过 → 该模式状态 = `gated` 或 `blocked`，STATE.next 指回对应阶段（多为 build）。

---

## Gate Function（取证纪律，来自 verification-before-completion）

```
在任何"通过/完成/修好"的措辞之前：
1. IDENTIFY  哪条命令能证明这个声明？
2. RUN       完整、全新地跑（不是子集、不是上次）
3. READ      读全输出 + 看 exit code + 数失败数
4. VERIFY    输出是否真的支持这个声明？
   否 → 报实际状态 + 证据
   是 → 报声明 + 证据
5. 才能说出口
跳过任何一步 = 说谎，不是验证。
```

**Iron Law：没有本轮新鲜验证证据，不得做任何完成声明。**

---

## 反合理化表（看到这些借口立刻 STOP）

| 借口 | 现实 |
|------|------|
| "现在应该能跑了" | 去跑验证命令 |
| "我很有信心" | 信心 ≠ 证据 |
| "就这一次" | 没有例外 |
| "linter 过了" | linter ≠ 编译器 ≠ 测试 |
| "覆盖率看着挺高" | 用 `--cov-fail-under` 让工具判，别肉眼读 |
| "agent 说成功了" | 看 git diff 独立验证 |
| "部分检查就够了" | 部分检查什么都证明不了 |
| "换个说法规则就不适用了" | 精神高于字面 |

红旗词：should / probably / seems to / "Great!" / "Perfect!" / "Done!" —— 出现在验证之前即违规。

---

## 好的样子

- 报告里每个 COVERED 都挂着本轮命令 + `34/34 passed` + `exit 0`。
- 覆盖率由 `--cov-fail-under=80` / `coverage.thresholds` 强制，输出里能看到工具自己 fail/pass。
- 发现的实现 bug 干净地 escalate 回 build，validate 的实现文件 0 改动。
- 每个修过的 bug 配一条会红绿验证过的回归测试，带 attribution。
- 三态清单完整，PARTIAL/MISSING 都写明缺口和下一步。

## 常见翻车

- 把"测试能 import / 组件能渲染"当作 COVERED（空断言）。
- 只跑改动文件那一个测试就宣布全绿，没跑全量 → 漏掉回归。
- 在 validate 里顺手改实现把测试改绿（应 escalate 回 build）。
- linter 过了就说 build 过（linter 不查编译）。
- 肉眼看覆盖率百分比，没让工具以 exit code 把关 → 阈值形同虚设。
- E2E 类行为塞进 correctness 硬跑，应该路由到 e2e 模式。
- bootstrap 失败却继续，假装"已测试"——必须报 BLOCKED。
- 单条 bug 死磕超过 3 次迭代，不 escalate。

## 介入哪些阶段

- **validate（主场）**：correctness 是 validate 的默认模式，每次都跑。
- **onboard**：被 `sdlc-onboard` 当 brownfield 基线健康检查调用，产出初始覆盖率/绿灯快照写进 PROFILE。
- **build（回流）**：暴露的实现 bug escalate 回 build 的 TDD↔调试子循环；修完再回 correctness 复跑。
- **review 之前**：correctness 全绿 + 覆盖率达标是进入 review 的前置门。

---

## 证据 schema：`.sdlc/validate/correctness-report.md`

```markdown
# Correctness Report: <feature/topic>
mode: correctness
updated: <stamp>
runtime: python | node-ts
test-commands: { unit: "pytest", coverage: "pytest --cov=app --cov-fail-under=80", build: "tsc --noEmit" }

## Summary
- result: PASS | GATED | BLOCKED
- tests: <pass>/<total> passed   (exit 0)
- coverage: lines <X>% (gate 80%) | branches <Y>% (gate 70%)  → PASS/FAIL
- build/typecheck: exit 0 | FAIL

## Requirement coverage (three-state)
| requirement / behavior | status | evidence (command + result) |
|------------------------|--------|------------------------------|
| <行为1> | COVERED | `pytest tests/x.py::test_a` → 1 passed, exit 0 |
| <行为2> | PARTIAL | 测试 failing：暴露实现 bug，已 escalate（见下） |
| <行为3> | MISSING | 无测试，建议路径 tests/y.py |

## Escalated implementation bugs (→ build)
- ⚠️ <现象> / 期望 <x> / 实际 <y> / 文件 <path> / 调试迭代 <n>/3

## Regression tests added
- <test file> — Regression: <id>，单独跑 green（exit 0）

## Coverage gaps / not verified
- <说明哪些没测到、为什么；非浏览器 smoke 用了什么手法>

## Gates
- [x] suite green (fresh)
- [x] build/typecheck exit 0
- [ ] coverage gate met
- [x] no impl changed in validate
- [x] regressions covered

## Next action
-> 覆盖率不达标，回 sdlc-build 补 tests/z.py  (或 -> sdlc-review)
```

---

## Codex / 可移植降级

- 全程只用 Read/Edit/Bash/Grep + git，无 Task/AskUserQuestion/gsd-tools/.planning 依赖。
- 需要用户决策时（如选测试框架）用 **text_mode**：纯文本编号列表让用户回数字，不调 AskUserQuestion。
- 无并行能力时（Codex）串行跑各步骤即可——correctness 本就是单 session 线性流程，无 fan-out。
- 所有产物落 `.sdlc/validate/correctness-report.md` 纯文件 + STATE.md，任何 caller 不依赖 Skill 机制即可续跑。
