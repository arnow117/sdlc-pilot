# ADR-0001: Use a dedicated SDLC control branch for cross-branch execution state

Status: accepted
Date: 2026-08-04

## 背景 / 问题

`.sdlc/STATE.md` 和在飞 plan 默认被 Git 忽略，适合单 worktree 的恢复，却不能在多个 clone 或 worktree 中阻止同一 requirements leaf 被重复领取。把任务运行状态放进 feature branch 也会让代码集成和协作元数据互相干扰。

## 决策

使用长期 `sdlc-control` Git 分支保存 `.sdlc-control/` 下的 request、requirements leaf、claim、feature、task 和 evidence 记录。领取和释放使用从最新控制提交发起的 fast-forward push；拒绝 force push。业务代码仍在 main、feature 和条件化 task branches 中演进。

批准后的 plan 先独立提交，再由下一次控制提交创建引用该 commit SHA 的 Feature/Task 记录。Task branch
只在依赖已验证、write set 不重叠、接口固定且 owner 唯一、runtime 可隔离、活动 Task 分支少于 3
时创建，否则在 Feature branch 串行执行。每次 Task 集成记录 source tip、merge method 和 resulting
integration SHA；验证证据不可修改，并精确绑定 tested SHA。

## 备选与否决理由

- 将 claim 写入 `main`：状态型提交会污染可发布主干，否决。
- 仅保存到各 feature branch 的本地 STATE：跨 clone 不能排他，否决。
- 使用外部 Issue/数据库：增加服务和凭据依赖，破坏纯文件 + Git 可移植约束，否决。

## 退化 / 保留

定义三种模式：`shared-control` 使用远端控制分支保证跨 clone 领取唯一性；`local-serial` 使用本地
控制记录但不声明跨 clone 唯一性；`legacy` 保留无 control branch 的旧行为且不自动迁移。保留 Feature
branch 上本地 `STATE.md` 作为 session 恢复快照，但它不再是全局协作事实源。Task worktree 使用只读
`TASK.md`，不能复制 Feature STATE。

## 架构影响 / 后果

新增一个固定控制分支和控制记录 schema，脚本必须处理 fetch、fast-forward push 竞争、缺失 ref 与 crash 后 stale claim。优点是 main 保持可发布、任务并行状态可跨 clone 查看，且所有持久状态都能通过 Git 审计和回滚。
