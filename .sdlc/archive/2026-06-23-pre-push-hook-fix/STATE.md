# SDLC State: 修 pre-push hook 误拦退场+合并收尾(Deferred #8)

stage: done
status: in-progress
work-type: hotfix
branch: fix/pre-push-retire-merge-gate
worktree: /Users/mac/hansen_agent_team/workspace/sdlc-pilot
source-leaf: (none)
updated: 2026-06-23
validate-modes: [correctness]
sdlc-gate: PASS reviewed-head=bba7f9f20e349380ed01f2fb69c4e7c958558b4e

## Gates passed
- [x] spec：hotfix 一段话(见 Decisions);evolve 升级而来,bug 已精确诊断
- [x] build：实现 + dogfood 6+1 场景红绿(放行/拦截两路)
- [x] validate：correctness(48测试+validate-skills)+ dogfood 7 场景
- [x] review：skill-maintainer+qa 无 CRITICAL/HIGH;qa 自审补无效-sha 守卫
- [x] verify：dogfood 证据全 + hook 纯 sh 硬门性质不变

## Active roles (from last diff scan)
- skill-maintainer (R10 改技能体系自身/钩子模板), qa (负路径:放行/拦截两路)

## Decisions log
- 2026-06-23 evolve 升级为 hotfix /sdlc(改 hook 门禁逻辑超 append-only 范围)。bug:pre-push hook 两处误拦合法退场+合并收尾——①retire 清栈后无 STATE 判"没走 SDLC";②retire/merge 提交推过 reviewed-head 判"评审后又改代码"。修:①无 STATE 但 .sdlc/archive/ 非空→放行;②reviewed-head..HEAD 非 .sdlc/ 代码无改动→放行。纯 sh,硬门性质不变。

## Next action
-> build:改 references/templates/hooks/pre-push + 同步 .git/hooks/pre-push + dogfood 红绿
