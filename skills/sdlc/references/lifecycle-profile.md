# Lifecycle profile protocol

适用于所有会在目标仓库写入 legacy、canonical、onboard、backlog 或 ship 状态的公开 SDLC 入口。唯一例外是
显式 preview：它仍严格只写 `.sdlc/preview/<run-id>/`，不读取或创建 lifecycle profile。

先运行 `lifecycle_profile.py --repo <target-repo> status`，并只按结果路由：

| 结果 | 行为 |
| --- | --- |
| `new-project-default` | 先运行 `init` 写入 dual profile；成功后才能启动 canonical product/delivery 流程。 |
| `configured / dual-lifecycle-v1` | 只走 canonical product/delivery ledger；不读取 legacy STATE 作为状态输入。 |
| `configured / legacy-0.19.2` | 只走 pinned legacy runbook / legacy control 协议。 |
| `migration-required` | 停止且零写入；要求用户用 `/sdlc migrate` 明确选择。 |

profile 选择是本地串行操作：运行 `init` 或 `migrate` 时，不能同时让旧版 agent、另一个 orchestrator 或手工脚本在同一
目标仓库写入 SDLC artifact。脚本用 `.sdlc/lifecycle.lock` 串行化 profile 选择；选择完成后，后续 writer 只能按固定
profile 的 lifecycle 执行。

不论调用者是否携带 `--authority dual-lifecycle-v1`，现有 artifact、preview 目录、legacy Markdown、control 分支或
ledger 都不能替代 profile。选择 dual 覆盖已有 artifact 时，必须先征得用户确认，再使用
`--allow-existing-artifacts`；该操作只写 lifecycle profile，不转换任何历史 artifact。
