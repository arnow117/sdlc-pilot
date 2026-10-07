# Feature 开发分支登记迁移

Requirement: `REQ-branch-registration`。方向来源与验收条件见 `REQ-branch-registration.product.md`。

## Plan

### 现状与复用决定

`scripts/lifecycle_state.py:start_feature` 只在创建时登记 branch；没有更新命令。`_mutate` 已提供 state 文件锁、staged/unmerged 拒绝、文件身份检查和原子替换；`_git`、`_repo_root`、`_require_context_file` 可复用。`retract_release` 已采用必填 reason、CLI 输出审计详情、工程上下文留正文和 Git 留历史的模式。

选择扩展现有实现，不引入依赖。外部框架不适用于一个状态字段的受控修正。state_version 保持 3，不新增字段、进度文件或运行时。

### 命令契约

新增 `migrate-feature-branch`，全局 `--repo` 固定到目标仓库根目录。必填 `--feature-id`、`--expected-branch`、`--branch`、`--expected-head`、`--reason`；沿用可选 `--at`。公开 Python API 对应 `migrate_feature_branch`。

- 只接受未 released/cancelled 的 Feature。
- 原登记必须精确匹配 expected-branch；branch 必须与旧值不同。expected-branch 只作旧值比较，不重新约束旧数据格式。
- branch 必须是显式合法的 Git 本地分支名，拒绝 Git 展开的 `@{-1}` 等表达式、特殊 HEAD、非法 ref。当前 symbolic HEAD 必须精确等于 `refs/heads/<branch>`，不把 tag/ref 或另一 worktree 上的分支误作当前 checkout。
- `--repo` 解析后的路径必须等于 Git 实际 worktree 根目录。Git HEAD 必须存在，且完整 commit ID 精确等于 expected-head。detached/unborn 不可迁移。普通 linked worktree 根目录应可用。
- 在所有身份与 staged 检查及 `_mutate` 之前拒绝会重定向仓库、index、对象或注入 config 的 Git 本地环境变量；采用 `git rev-parse --local-env-vars` 声明的变量集合并补充 `GIT_NAMESPACE`。不能只检查 show-toplevel 而使 branch/HEAD 或 staged 检查来自另一仓库/index。保留普通代理、认证与非仓库身份环境。只约束新增命令，不改变旧命令的环境行为。
- 使用原 `_mutate` 安全机制，在锁内检查旧值及工作区身份。完成前复核 branch/HEAD/root；不与人工同时 checkout，现有 state 锁不锁 Git。不要引入 Git 锁协议。
- 工程上下文必须仍是存在的普通安全路径。允许其他代码和上下文未提交，不调用 `_code_head`，不把在途登记修正视作验证。
- 唯一持久化变更是该 Feature 的 branch 与 updated_at；Requirement、Task、validation/review/release、其他 Feature 与 schema 原样保留。
- 返回 operation、Feature、旧/新 branch、reason、实际 HEAD、规范仓库路径、时间与工程上下文路径。CLI 只写 state，不自动写 Markdown 或做 Git 操作，避免多文件部分提交。
- 主 Agent/独立维护者先在原工程上下文保存本次迁移决定、完整参数、原因及预期 HEAD，再调用命令；成功后追加返回的实际结果，按既有授权与 state 一起纳入 Git。失败或中断后先只读核对 state 与 Git，区分原调用证据和事后观察，不推断丢失的实际 HEAD 或原因，不重复旧值迁移或伪造验收。
- 写入前校验拒绝保证 state 字节不变；原子替换后的目录 fsync/输出失败可能已改 state，属于结果不确定。保留现有 writer 行为，明确这种边界并做有限故障注入，不把错误退出普遍等同于未写入。

### 阶段与派工语义

权威分支规则放在现有 `lightweight-runtime.md`；router、Plan、Build 与 stage-agent-protocol 引用该规则。

只读 status/next/projection/backlog 不要求当前分支一致、不修改登记。Plan 选择实际开发分支；Build 和恢复到开发时先核对登记、实际 root/branch/HEAD，分支不一致需回到登记分支或由主 Agent 明确迁移，再派工。brief 区分开发分支、实际执行工作区/HEAD、执行用途、发布目标；历史未收口 Feature 数不等于活动 worker 数。

迁移前主 Agent 先等待或停止同一 Feature 的活动写入者，处理未验收结果并保持 Task/失败历史；迁移后按实际工作区重新发完整 brief，使旧 worktree 的产出不能无条件继续被接受。独立维护者同样确认该 Feature 没有其他活动写入。该条件由编排者负责，不新增 worker 注册状态或限制其他 Feature 的并行资格。

Validate/Review/Ship 以被验证实现 commit 和现有代码差异规则判断；发布目标分支、detached 验证 checkout 不为此重登记 Feature，不增加全局分支拒绝检查。迁移后代码若不同，review/release 原有版本检查继续拒绝，必须重做适用验证。已 released/cancelled 的历史登记不改 main。

项目按需求串行交付是项目策略，不删除通用并行资格。HappyCompany 完全在写范围外。

### Task 与写范围

`TASK-branch-registration`：一个独立可验收的命令、测试和必要文档增量。写范围：`scripts/lifecycle_state.py`、`scripts/test_lifecycle_state.py`、`skills/sdlc/SKILL.md`、`skills/sdlc/references/lightweight-runtime.md`、`skills/sdlc/references/stage-agent-protocol.md`、`skills/sdlc-plan/SKILL.md`、`skills/sdlc-build/SKILL.md`、`docs/specs/2026-08-10-lightweight-sdlc.md`、`README.md`、`CHANGELOG.md` 及本工程上下文的证据章节。

保留初始 staged/unstaged 改动，尤其 Plan/Build、README、CHANGELOG 的既有 2.0.0 内容；只追加必要段落，不改 index、不 commit/push/checkout、不改版本元数据。新增能力在 Unreleased 说明兼容性；发布时再按真实远端版本和既有 SemVer 流程决定 minor 或纳入尚未发布的版本。源码主工作区当前为 main；本任务不切换共享工作区。

### 验收与测试

使用现有 unittest 临时 Git repo 与真实 CLI，无模型或网络依赖。覆盖成功和审计输出、Task/失败/通过验证及 review 保留、其他 Feature/Requirement 保留、旧值冲突/重复迁移/同旧值两个 writer、非法分支/未实际检出/detached/HEAD 冲突/unborn/错误 repo root、closed Feature、staged/冲突 state、缺失/符号链接工程上下文、linked worktree、Git 仓库与 index 环境重定向。所有写入前校验拒绝路径 state 字节不变；注入替换后 fsync/输出失败，证明恢复必须先查实际状态。

证明查询在不一致和 detached checkout 上仍只读，现有 validated commit 在发布分支/detached 环境继续有效，而迁移到代码不同的分支不能绕过 review/release 版本检查。验证 CLI help 和文档实际命令。

公开 README 的迁移入口使用稳定的全局 scenario ID，导航到本 Requirement 已有 SCN-1～6 与验收条件；参数继续引用权威 runtime 操作指南，不复制规格或新增产品故事。

运行 `bash scripts/validate-skills` 与 `git diff --check`，按 dirty baseline 复核只追加本次增量，并用独立只读 reviewer 复核安全性和兼容性。必要更改后的受影响测试重跑。无额外格式化配置时保持现有 Python 风格。

### 风险与回退

登记迁移不是 Git checkout，state 文件锁不能阻止人工同时切换 Git；执行时保持 worktree 身份稳定，检查不提供分布式事务。原子 state 修改或输出后中断时，先查询实际登记；预先保存在工程上下文中的决定与事后观察分开记录，不宣称重建不存在的调用证据，不加第二日志。回退登记使用同一显式命令、实际 checkout 和新的预期旧值，不清空已有交付信息。

代码完成后当前源仓库仍 dirty，state/context 未 tracked 时不能记录 validation pass。先完成工作区测试与独立复核，再按授权提交明确文件，才可依序完成 Validate/Review/Ship。未授权插件发布时不宣称已发布。

发布后观察：后续维护者在真实恢复场景核对一次命令拒绝/成功、交付证据与版本校验；新问题回流 Requirement，不建立持续监控。

## 实施决定与证据

基线 HEAD: `bd3d2bb486efb921c8810874addedf4513185bef`。基线 `bash scripts/validate-skills` exit 0：15 lifecycle、7 backlog、36 contrast 测试；`git diff --check` exit 0。现有 Codex/Claude 全部 SDLC 技能是指向当前源码 skills 目录的软链，修改原文件即生效，无需复制或新安装。

准备期间其他对话提交了既有 2.0.0 变更，源码当前 HEAD 为 `a034dc6cddf3784fb257890e1d09d2c79d4e65f3`；保留该提交。本次独立的只读公共契约复审提出 Git 环境重定向、替换后结果不确定、预存审计决定、同 Feature 活动写入交接四项问题，已收紧上述 Plan。实际 `git rev-parse --local-env-vars` 和 `git check-ref-format --branch` 行为已只读核对。

实现工作快照基于 `a034dc6cddf3784fb257890e1d09d2c79d4e65f3`。先运行
`PYTHONDONTWRITEBYTECODE=1 python3 scripts/test_lifecycle_state.py LifecycleStateTest.test_migrate_feature_branch_updates_only_the_open_feature_registration`，
新增测试以缺少 `migrate_feature_branch` 的 `AttributeError` 失败；实现后该测试通过。最终
`PYTHONDONTWRITEBYTECODE=1 python3 scripts/test_lifecycle_state.py` exit 0（30 tests），涵盖成功审计、字段保留、
旧值/关闭/并发 writer、ref 与 checkout 身份、环境重定向、context、state 安全、linked worktree、故障恢复，以及
detached validation/release 与不同实现不能绕过已批准交付。`bash scripts/validate-skills` exit 0，
`git diff --check` exit 0；`python3 scripts/lifecycle_state.py migrate-feature-branch --help` 实测显示全部参数及其
“只更新登记、不 checkout/验收/改上下文”的含义。测试只在临时 Git fixture 中创建分支、提交、checkout 和 worktree。

本源工作树仍含本 Feature 的未提交源码/文档修改、本次初始化的未跟踪 `.sdlc-v1/`，以及原有
`happycompany-markdown-catalog.md`。worker 没有直接写 `state.json`；正常生命周期状态由主 Agent 通过 CLI 管理。
没有记录 source validation pass，没有 commit、push 或发布。

独立预提交复核后的测试修正未改运行时代码：`scripts/lifecycle_state.py` SHA-256 仍为
`a996fc86183101c29161776c87c42b9b2963b2b4d400cf1ac25d4e5766f8f74c`。环境测试现以清空后的单变量环境分别覆盖
`GIT_INDEX_FILE`、`GIT_DIR`、namespace 和每个 config 注入变量，并在每例断言精确的环境拒绝与 state 字节不变；
对仅移除 `GIT_INDEX_FILE` guard 的内存变体，受控 `_repo_root` 探针被触达，证明该例不会被其他变量掩盖。不同实现迁移的
场景保留迁移前 approved review，断言迁移只保留交付字段，并分别拒绝新的 review 与 release。修正后
`PYTHONDONTWRITEBYTECODE=1 python3 scripts/test_lifecycle_state.py` exit 0（30 tests），
`bash scripts/validate-skills` exit 0（30 lifecycle、7 backlog、36 contrast），`git diff --check` exit 0。

主 Agent 最终验收：命令、兼容性文档与测试满足上述实现契约；独立只读 reviewer 未发现阻塞性功能、安全或兼容性问题。
reviewer 提出的单变量环境测试掩盖问题已由原 worker 修正，主 Agent 已复核修改及完整测试证据。
最终测试文件 `scripts/test_lifecycle_state.py` SHA-256 为
`cb6ed47ac60b3cf66730c6ecc0e4b7d49f951d7ea924299e1cb84ba2494252ed`；运行时哈希保持上述值。
源码修改共 10 个已跟踪文件；Codex 与 Claude 的已安装 SDLC 技能仍软链到本源码，无需重新安装。

主 Agent 通过正常 CLI 将 `TASK-branch-registration` 标记 done，下一阶段为 Validate。
这表示本次实现任务完成；Feature 的 validation、review、release 记录仍 pending。
当前源码及正常生命周期目录尚未提交，不能把工作区测试或本次预提交复核登记为正式阶段通过。
后续按既有提交授权将明确文件纳入 Git，再依序执行 Validate、Review、Ship。
本次没有改动 HappyCompany 的源码、状态、登记分支或 Goal，也没有向其他对话发送消息。

## 提交与推送授权

2026-10-07 用户明确授权“推上去吧把 sdlc”，覆盖本次源码、必要文档与正常生命周期记录的提交和推送。
当前源码分支为 main，远端为 origin（arnow117/sdlc-pilot）；提交前 fetch 确认 HEAD 与 origin/main 一致。
原有未跟踪 `happycompany-markdown-catalog.md` 留在原工作区，不提交、不忽略、不删除。
正式验证使用同一实现提交的干净 detached checkout，避免无关文件影响 Git 前置条件；这不是开发分支迁移。
本次授权为仓库提交推送，CHANGELOG 保持 Unreleased，不创建插件版本 tag 或 GitHub Release。

## Validation

### Correctness — d082f05a56f3c065d2a063ae6edfcf02c3ab90ac

执行时间：`2026-10-07T13:25:20Z`。验证在干净 detached linked worktree
`/Users/arnow117/hansen_agent_team/workspace/20261007-sdlc-branch-validation-b2wse932` 运行；`git status --porcelain=v1`
在写入本节前为空，开发登记仍为 `main`，执行用途仅 Validate，不触发分支迁移。运行环境为 Python `3.9.6`、Git
`2.50.1 (Apple Git-155)`；无项目 typecheck、build、coverage 配置，也无本次改动涉及的 Web/App/模型旅程，因此
`correctness` 是适用方式，e2e/eval-bench 不适用。

| command | result | observed result |
|---|---|---|
| `bash scripts/validate-skills` | PASS (exit 0) | 30 lifecycle、7 backlog、36 contrast tests 通过；技能结构、Markdown 引用、编排与可移植性检查通过。 |
| `git diff --check` | PASS (exit 0) | 检查写入本节前的干净验证 worktree；无当前工作树 whitespace error。 |
| `git diff --check a034dc6cddf3784fb257890e1d09d2c79d4e65f3 d082f05a56f3c065d2a063ae6edfcf02c3ab90ac` | PASS (exit 0, main Agent) | 显式检查被测提交相对基线的 diff；无 whitespace error。 |
| `python3 scripts/lifecycle_state.py migrate-feature-branch --help` | PASS (exit 0) | 显示五个必填身份/原因参数和可选 `--at`，并说明不 checkout、不验收、不改工程上下文。 |
| `python3 scripts/lifecycle_state.py record-validation --help` | PASS (exit 0) | 显示 `--feature-id`、`--result` 必填，`--test-command`、`--commit`、`--at` 可选。 |
| 完整 temporary coverage 流程（如下） | PASS (all exit 0) | 临时 `/private/tmp` 工具环境的 Coverage.py 7.16.2（Python 3.12）采集 30 个 lifecycle tests，含 CLI 子进程数据；不修改项目依赖、配置或报告。 |

Coverage 只使用 `/private/tmp/sdlc-coverage-cache` 的 `uv` cache 和
`/private/tmp/sdlc-branch-validation-coverage-v2` 的一次性 artifacts；它们不是仓库文件、lifecycle state 或第二进度记录。
该目录的 `.coveragerc` 为：

```ini
[run]
branch = True
parallel = True
source =
    scripts
relative_files = True
```

`sitecustomize/sitecustomize.py` 只有 `import coverage` 和 `coverage.process_startup()`，使测试的真实 CLI 子进程也向同一
临时数据目录写入。实际运行、合并和 JSON 命令为：

```bash
UV_CACHE_DIR=/private/tmp/sdlc-coverage-cache \
COVERAGE_PROCESS_START=/private/tmp/sdlc-branch-validation-coverage-v2/.coveragerc \
COVERAGE_FILE=/private/tmp/sdlc-branch-validation-coverage-v2/.coverage \
PYTHONDONTWRITEBYTECODE=1 \
PYTHONPATH=/private/tmp/sdlc-branch-validation-coverage-v2/sitecustomize \
uv run --isolated --with coverage coverage run \
  --rcfile=/private/tmp/sdlc-branch-validation-coverage-v2/.coveragerc \
  scripts/test_lifecycle_state.py

UV_CACHE_DIR=/private/tmp/sdlc-coverage-cache \
uv run --isolated --with coverage coverage combine \
  --rcfile=/private/tmp/sdlc-branch-validation-coverage-v2/.coveragerc \
  --data-file=/private/tmp/sdlc-branch-validation-coverage-v2/.coverage \
  /private/tmp/sdlc-branch-validation-coverage-v2

UV_CACHE_DIR=/private/tmp/sdlc-coverage-cache \
uv run --isolated --with coverage coverage json \
  --rcfile=/private/tmp/sdlc-branch-validation-coverage-v2/.coveragerc \
  --data-file=/private/tmp/sdlc-branch-validation-coverage-v2/.coverage \
  -o /private/tmp/sdlc-branch-validation-coverage-v2/coverage.json
```

统计读取这个 JSON，并将 `git diff --unified=0 a034dc6..d082f05 -- scripts/lifecycle_state.py` 的新增行交集限定为
coverage statement lines；branch arc 只计 source line 在新增行的 arc。实际统计脚本方法为：

```python
import json, re, subprocess

base = "a034dc6cddf3784fb257890e1d09d2c79d4e65f3"
head = "d082f05a56f3c065d2a063ae6edfcf02c3ab90ac"
patch = subprocess.run(
    ["git", "diff", "--unified=0", base, head, "--", "scripts/lifecycle_state.py"],
    check=True, text=True, capture_output=True,
).stdout.splitlines()
added, new_line = set(), None
for line in patch:
    match = re.match(r"^@@ -\d+(?:,\d+)? \+(\d+)(?:,\d+)? @@", line)
    if match:
        new_line = int(match.group(1))
    elif new_line is not None and line.startswith("+") and not line.startswith("+++"):
        added.add(new_line)
        new_line += 1
    elif new_line is not None and not line.startswith("-"):
        new_line += 1

report = json.load(open("/private/tmp/sdlc-branch-validation-coverage-v2/coverage.json"))
details = report["files"]["scripts/lifecycle_state.py"]
executed = set(details["executed_lines"])
statements = executed | set(details["missing_lines"])
arcs = details["executed_branches"] + details["missing_branches"]
executed_arcs = set(map(tuple, details["executed_branches"]))
changed_statements = added & statements
changed_arcs = {tuple(arc) for arc in arcs if arc[0] in added}
print(len(added), len(changed_statements), len(changed_statements & executed))
print(len(changed_arcs), len(changed_arcs & executed_arcs))
```

Coverage 只计算 `a034dc6..d082f05` 中 `scripts/lifecycle_state.py` 的 189 个新增文本行里被 coverage 识别为可执行的
71 行，以及源行位于新增分支点的 28 条 branch arc；不是全仓库覆盖率。执行 70/71 行（98.6%，默认 80% 以上）和
27/28 branch arc（96.4%，默认 70% 以上）。唯一缺口是 `_current_branch_migration_identity` 中 `git rev-parse
--show-toplevel` 失败后拒绝的 arc（507→508）；其余新增身份、环境、锁内复核、成功审计与 CLI 分支均被测试覆盖。

| 产品验收条件 | status | 本轮证据 |
|---|---|---|
| 1. 匹配身份时仅更新目标登记并提供审计 | COVERED | `test_migrate_feature_branch_updates_only_the_open_feature_registration` 与 `…preserves_delivery_evidence_and_other_records` 在临时真实 Git repo 断言 branch/updated_at、审计输出和其余交付字段。 |
| 2. prewrite rejection 确定且 state 不变 | COVERED | 身份/ref/HEAD/root、closed Feature、context、staged/unmerged、Git 环境重定向和锁内身份变化测试均断言拒绝；prewrite 路径断言 state bytes 不变。 |
| 3. 同旧值并发只有一个成功 | COVERED | `test_migrate_feature_branch_cli_help_audit_and_two_writers` 在同一临时 checkout 启动两个真实 CLI，观察到 return codes `[0, 2]`。 |
| 4. active-writer 交接和新 brief | COVERED | 实现的可执行边界为编排文档：`lightweight-runtime.md`、`stage-agent-protocol.md`、Plan/Build 均要求先交接同 Feature writer，再以实际 root/branch/HEAD/用途重发完整 brief；本 Validate brief 本身使用 detached worktree，未迁移开发登记。 |
| 5. 替换后失败按结果不确定恢复 | COVERED | `…marks_postreplace_failures_as_recovery_cases` 与 `…marks_output_failures_as_recovery_cases` 注入 fsync/输出失败，证明 state 可能已写入；README/runtime 规定只读恢复、禁止自动重试。 |
| 6. 非开发或 detached 查询保持可用，版本规则不变 | COVERED | `test_branch_migration_does_not_add_global_branch_rules_to_queries_or_delivery` 覆盖 detached validation/release 和查询；`…cannot_bypass_approved_delivery` 分别拒绝不同实现后的 review/release。 |
| 7. 范围、依赖和工程审计完整 | COVERED | 产品上下文列明无未决问题；已接受 Plan、此 Task 和本次固定 detached Validate brief 均保持同一范围。 |
| 8. help、说明、兼容性与确定性测试一致 | COVERED | 本轮实际 help、README/runtime/Plan/Build/protocol 的引用检查，以及 `validate-skills` 与 30 个 lifecycle tests 通过；state 仍为 version 3。 |

Outcome: `PASS`。未发现实现缺陷或环境阻塞；覆盖缺口低于默认阈值但已精确记录。以上仅证明临时真实 Git/CLI
fixture 与本地标准检查，不证明 live 部署、插件发布、网络服务或真人使用。主 Agent 已将同一被测提交正常推送到
`origin/main` 并用 `git ls-remote` 核对完整 hash；这不创建插件版本、tag 或 Release。此 worker 尚未调用
`record-validation`、修改 `state.json`、commit 或 push；由主 Agent 在验收后执行允许的状态转换。

## Review — d082f05a56f3c065d2a063ae6edfcf02c3ab90ac

独立 reviewer `branch_contract_review` 核对了提交与 validation 绑定、干净的业务工作树、运行时与最终测试哈希。
原四项风险已解决，单变量环境与不同实现拒绝测试有效；独立重算 coverage 为 70/71 行、27/28 branch arc。
本次 diff 未发现有证据支持的重复实现或可避免工程债，验证范围及唯一覆盖缺口均已明确记录。

发现一项 P2 公开使用契约缺口：README 新命令入口缺少稳定 scenario ID 到既有产品故事和验收条件的导航。
参数与 CLI 一致，但 guide → story → parameter → actual-use evidence 链条未完整；依据 software-delivery 的全局 usage 契约，
返回 Build，在现有 README 章节补稳定 ID、已有 SCN-1～6 和 AC 链接，随后重新验证对应提交。
主 Agent 接受 `changes_requested`，保留本次验证与评审事实，不修改运行时、测试或产品故事范围。
