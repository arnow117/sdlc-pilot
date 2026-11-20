# FEAT-human-validation 独立 Review 记录

- 候选：`f62b6fee0d99bb81e5b15307a34021e004a7f79b`；累计基线：`e587eb1a2abf6ca40b3f0b790f902f3c64e349c6`。
- 独立执行者：T3 `codex / gpt-6.2-sol / reasoningEffort=xhigh`，宿主终态 `executedModel=gpt-6.2-sol`。[完整原生评审](t3-thread://v2/cb0ab126-b88e-4134-8282-a4e59f62c293/thread:delegated-task:command%3Amcp%3Aa919fc85-eb27-47f2-b212-4d7af9bab58a%3Adelegate-task%3Aa7291223-8786-4a33-bef6-bc105654f7fd)。
- 结论：`changes_requested`；四项 P2 必修，另有两项 P3 建议。既有本地范围 Validate 已通过；真人样本仍待答复，合成共同 I 未运行。

## 必须修复

1. **P2，检查点清理。** `skills/sdlc/references/templates/CHECKPOINT.md:4` 将清理时机写为 Feature 完成，未明确已发布但登记回执尚未核实时仍须保留；与共享协议 §6 的未决回执恢复条件冲突。修正模板并验证已发布、回执未核实的恢复路径。
2. **P2，审阅面板场景列表。** `skills/sdlc-prototype/assets/review-console/review-console.js:1407` 对整组场景摘要直接 JSON 序列化；一个不可序列化场景可使 `review-panel.js:385` 挂载失败，其他合法场景无法使用。应逐项隔离无效项，在面板展示可序列化的错误，并保留合法场景和已有运行；从真实面板入口验证无效项不会重置产品。
3. **P2，观察失败导致动作重复。** `review-console.js:994` 与回看路径在记录失败前格式化不可序列化的观察值会抛错。动作已经成功但状态仍可继续，下一次 `next()` 会重复执行。应在共用观察处理处安全处理值，让正常推进和回看沿失败分支停止；验证第一次失败、动作仅调用一次、后续不重复。
4. **P2，桌面工单筛选身份。** `examples/desktop-ticket-desk.js:86` 按当前角色归属工单，但 `:179` 和 `examples/ticket-desk-console.html:215` 的「我受理的」固定筛选林岚。复核专员受理 T-102 后筛选会显示 T-103 而隐藏 T-102。应统一角色身份及页面/计数的可见列表逻辑，并经普通控件验证工单 ID 和计数。

## 建议改进

- **P3，历史评审事实。** `scripts/test_scenarios.py:619` 的恢复检查允许同 Feature、同 commit 的 `pending by None` 作为原评审事实；应验证引用确有已作出的评审决定并增加反例。
- **P3，工程正文链接。** `FEAT-human-validation.engineering.md:155,169,188` 的三处 `../../workspace/…` 在仓库解析不到对应证据；应修正为可读定位，并按批准型重记规则处理正文指纹。

## 主 Agent 核对

- 只读源码核对了模板、场景序列化、观察失败前的序列化及桌面两处固定身份筛选。
- 在固定 Node 22 镜像的禁网、非 root、只读容器中，针对冻结候选执行定向探针：无效场景使 `listScenarios()` 抛 `TypeError`；两次 `next()` 分别抛异常且产品动作累计调用两次；复核专员受理 T-102 后当前固定筛选仍指向 T-103。容器已回收。原始输出及镜像、参数、退出码在本任务 `continuation/formal-validation-f62b6fe-r3/review-findings-probe.*`。
- 上述探针验证了问题的可观察后果；真人试用、生产环境和跨机器授权不在其覆盖范围内。
