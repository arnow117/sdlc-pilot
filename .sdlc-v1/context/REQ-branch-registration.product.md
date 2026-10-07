# Feature 开发分支登记迁移

## 问题与目标

已有未收口 Feature 的实际开发分支可能已经变化，而 lifecycle state 的 `branch` 登记仍是旧值。恢复和派工若继续使用旧登记，会在错误的开发上下文工作。

本需求为负责 lifecycle state 的主 Agent 或独立维护者提供一次显式、最小的登记迁移。成功意味着：确认身份后，只有目标 Feature 的分支登记和更新时间改变；原交付证据和历史保持可追溯。

## 方向来源与结果

方向来源是用户授权的分支登记迁移请求，以及当前 `FEAT-branch-registration.engineering.md` 的已协调实现前审查。后者是工程命令、测试和安全细节的权威来源；本文件不重复实现方案。

成功指标是一次成功迁移可报告实际开发身份和审计事实；身份或前置条件不成立时，调用者可观察到拒绝且原 state 不变。迁移后在下一次真实恢复中，由维护者核对登记、实际 checkout 和完整 HEAD；观察到的问题新建 Requirement，不建立持续监控。

## 范围

范围内：

- 对未 closed 的单个 Feature，将已登记的旧开发分支修正为当前实际 checkout 的新开发分支。
- 将预期旧登记、实际 checkout、规范仓库根目录、完整当前 HEAD、目标新分支和原因作为一次迁移身份的一部分。
- 保留 Task、Requirement、validation、review、release、其他 Feature 和 Git 历史；迁移决定与结果写入该 Feature 已有工程上下文。
- 在同一 Feature 更换实际工作区前完成 active-writer 交接，并让后续派工使用新的实际身份。

范围外：

- 自动 checkout、自动同步 branch、hook、守护进程、第二状态/事件系统或 schema 迁移。
- 修改已 released 或 cancelled Feature 的历史登记，批量改写多个 Feature，或把分支登记当作代码验收、发布或版本回退。
- 修改 HappyCompany、其 lifecycle state、Goal、历史 worktree 或源码；本需求也不授权 commit、push、发布或合入 main。

## 术语与规则

| 术语 | 含义 |
|---|---|
| 登记分支 | lifecycle state 中该 Feature 当前保存的开发分支值；它可能落后于实际 checkout。 |
| 实际 checkout | 发起迁移的工作区当前 symbolic 本地分支、规范仓库根目录和完整 HEAD 的组合。 |
| 迁移身份 | Feature、预期旧登记、实际 checkout、新分支、原因和完整 HEAD；任一不一致都不能写 state。 |
| prewrite rejection | 状态文件替换之前发现的身份、Feature 状态、state 安全性或 Git 仓库/index 重定向环境问题。 |
| 结果不确定 | 状态替换之后发生中断或输出失败，调用者不能从错误退出推断“未写入”。 |

规则：

1. 新分支必须就是发起迁移工作区当前实际检出的开发分支；迁移不替任何人执行 Git checkout。
2. 预期旧登记必须精确匹配，且新旧分支必须不同。同一 checkout 的同一 state 文件上，并发或重复调用使用相同预期旧值时，至多一个调用可以成功；跨 clone 的独立 state 仍由普通 Git 合并处理。
3. 迁移必须拒绝任何会把 Git 仓库、worktree、index、对象或配置解析重定向到当前 checkout 之外的本地环境变量；拒绝不尝试修复环境。
4. released/cancelled Feature、detached 或 unborn checkout、错误仓库根目录、完整 HEAD 不匹配和不安全 state 都不能迁移。
5. 只读状态查询仍可在其他开发/发布分支或 detached checkout 使用；这些查询不要求、也不触发登记迁移。
6. 迁移不改变被验证的实现版本。若新开发分支的代码与既有验证版本不同，现有 review/release 校验仍要求适用的重新验证。

## 用户场景与具体例子

### SCN-1：确认身份后登记当前开发分支

Given 一个未 closed Feature 的登记分支仍是 `feature/old`，维护者位于目标仓库的实际 `feature/new` checkout，且记录的规范根目录、完整 HEAD 与预期旧登记均匹配。

When 维护者提供新分支、原因和该完整 HEAD 进行一次迁移。

Then 该 Feature 的登记分支变为 `feature/new`，其更新时间变化，输出可观察地包含旧/新分支、原因、实际 HEAD 和仓库根目录；所有 Task、Requirement、validation、review、release 与其他 Feature 保持原值。

### SCN-2：写入前身份不成立

Given 预期旧登记、实际 checkout、规范根目录、完整 HEAD、Feature 状态、state 安全性或 Git 仓库/index 重定向环境中任一条件不成立。

When 维护者尝试迁移。

Then 调用在 state 文件替换之前被拒绝，目标 state 的内容保持不变；输出指明拒绝原因，维护者先修正身份或环境，再重新进行只读核对。

### SCN-3：两个维护者使用同一个旧登记

Given 两个维护者都对同一 checkout 的同一 state 文件，以同一 Feature 和同一预期旧登记开始迁移。

When 其中一个维护者先完成迁移，另一个维护者随后抵达写入前检查。

Then 后一个维护者因旧登记已不匹配被拒绝，不覆盖先完成的登记，也不改变交付证据。

### SCN-4：同一 Feature 的 active writer 交接

Given 同一 Feature 已有活动写入者，或已有尚未验收的结果绑定旧工作区。

When 主 Agent 决定迁移登记。

Then 它先等待或停止该写入者、处理其未验收结果并在工程上下文完成迁移前审计；迁移成功后，旧工作区产出不能被无条件接受，后续完整 brief 必须列明新的实际 checkout、仓库根目录、开发分支、完整 HEAD 和执行用途。

### SCN-5：状态替换后的结果不确定

Given 所有写入前身份检查已通过，但在 state 替换之后进程中断或输出失败。

When 调用者收到错误或没有可用的成功输出。

Then 调用者把结果标记为不确定，不自动重试同一预期旧登记，也不声称 state 未变化；它先只读恢复，核对实际登记与当前 checkout/root/full HEAD，再把观察结果追加到既有工程上下文并决定下一步。

### SCN-6：非开发 checkout 的只读恢复

Given 维护者处于发布分支或 detached 验证 checkout。

When 它查询 lifecycle state、验证记录或投影。

Then 查询保持可用且不修改登记；它不会因为当前不是登记开发分支而创建迁移。

## 迁移前审计与交接

一次迁移的预先决定放在被迁移 Feature 的 `engineering_context_ref` 指向的既有实施决定/证据章节中，不写入本工具 Feature 的 Plan，不新增日志或状态文件。主 Agent 或独立维护者在写入前记录完整参数、原因、预期 HEAD、当前交付证据与活动写入交接结论；成功后记录返回的实际结果。写入前拒绝与结果不确定必须分别记录，不能以错误退出代码把两者混为“没有写入”。

## 非功能要求

- 安全性：身份不一致或 Git 仓库/index 重定向环境必须在 state 写入前被拒绝。
- 一致性：同一 state 文件上同一预期旧登记的并发调用不允许后到者覆盖先到者；迁移只改变登记字段和更新时间，不提供跨 clone 事务。
- 可恢复性：替换后的中断只能通过只读状态与 Git 观察恢复判断，不重建未观察到的调用事实。
- 可观测性：成功提供 Feature、旧/新分支、原因与实际身份；拒绝明确失败原因，结合调用前保存的决定核对。详细决定留在目标 Feature 既有工程上下文，Git 保存其历史。

## 验收条件

1. 给定匹配的迁移身份，维护者可观察到仅目标 Feature 的登记分支与更新时间改变，以及完整审计结果。
2. 每个 prewrite rejection 条件都有确定的拒绝结果，且可由测试证明 state 不变。
3. 同一 checkout 的同一 state 文件上，并发/重复使用同一预期旧登记时，只有一个调用可成功。
4. active-writer 交接在迁移前完成；迁移后的派工不复用旧工作区的未验收结果。
5. 状态替换后的中断或输出失败被视为结果不确定，恢复流程只读核对实际 state 与 Git 身份，不自动重试或伪造成功/失败结论。
6. 普通只读查询在非开发分支或 detached checkout 仍可用；迁移不改变验收、review 或 release 的现有版本要求。
7. 本范围、依赖和工程审计已经明确，没有需要用户补充才能开始实现的产品决定。
8. CLI 帮助和 Plan/Build/恢复/派工说明与实际命令一致，确定性测试覆盖上述行为。旧命令和 state_version=3 保持兼容；已安装技能复用现有源码链接与发布流程，不安装第二套生命周期。

## 依赖与未决问题

依赖：现有 `.sdlc-v1` state、安全写入机制、Feature 工程上下文和普通 Git 身份查询。

未决问题：无。具体命令参数、错误文本、函数结构和测试注入方式由现有工程 Plan 约束并在后续 Build 验证。
