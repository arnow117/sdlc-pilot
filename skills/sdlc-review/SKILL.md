---
name: sdlc-review
description: >
  兼容适配器：保留 /sdlc review 的精确 0.19.2 多角色评审流程。
  新评审 preview 只有通过显式 sdlc-software-delivery 调用才可运行，不能改变 legacy review 或 ship 状态。
---

# sdlc-review — legacy compatibility adapter

默认 /sdlc review 先加载固定且校验过的 legacy runbook：

    python3 <sdlc-pilot-root>/scripts/legacy_runbook.py \
      --repo-root <sdlc-pilot-root> show --stage review

它保留原有的多角色评审、tested_sha / integration 关联以及
[control-plane.md](../sdlc/references/control-plane.md) 语义。固定对象不存在时明确失败；不能在普通 review
中隐式运行新的 reducer、批准或变更请求。

显式 `/sdlc software-delivery --phase review --authority dual-lifecycle-v1` 才能对已验证的当前 tuple 记录
canonical review。公开请求只能是 `submit_feature_review`：由 authority config 的 `feature_review/feature` policy
解析 reviewer，且 attestation 必须绑定当前 fence 与全部通过的 Evidence；不能直接提交内部 `review_feature` 或
caller 自报的 reviewer identity。`/sdlc preview delivery --phase phase.delivery.review …` 仍只能做
software-delivery preview；preview attestation 和报告只能写 .sdlc/preview/<run-id>/，不能作为 legacy review PASS、
release candidate 或 ship 的依据。
