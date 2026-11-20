# 恢复检查点：FEAT-human-validation

## 定位

- 仓库：/Users/mac/hansen_agent_team/external/sdlc-pilot；branch：main；HEAD：a0968a3（仅保存验证和复评证据）；控制台与测试有未提交返修，待固定新候选。
- Requirement：REQ-human-validation；Task：TASK-human-validation

## 已确认

- 用户对有限 Build/Router 调整、本地候选提交及 benchmark 预算调整回复“没问题”。
- 用户随后同意本批最多 43 run、比较组新试次启动窗口先延至 150 分钟、后延至 210 分钟；仍为原定 14 个试次、并发 1，详见试次台账。
- 随后用户明确表示“给你无限的预算，完成验收”；允许为完成验收继续必要的模型调用和补充试次，旧批次 14 次及 43 run 的历史如实保留。候选外未提交修改继续保留；未新增 push、部署或真实发布授权。
- 原 Plan 的批准正文与 f62b6fe Git 对象逐字节相同；工程旧 context-v1 为 `11e1b6405436252b13bb3ac62a00553c6166a3b8d451923a3faf451317153e63`，产品为 `c82fda329e5f53866434dcc53a745f813bbd2a4c5aa9ab73d7dc0d624475f903`。
- 返修 Plan 核准对象：原联合候选及用户继续完成验收的范围内修复评审发现，产品不变；已重记 `plan`，工程 context-v1 为 `9ffa2a2e39ddacca83237eb1c7e26fc3bcfe754df04620f8135cd5043182201a`，产品沿用上值，调用前后与预核准映射逐项一致。变更和授权见 `repair-plan-approval.json` 与 `repair-plan.diff`。
- 用户允许暂时换回冻结文件、登记 fail 后原样恢复。2026-11-20T11:21:16Z 原 CLI 记录 validation `fail`，绑定 `f62b6fee0d99bb81e5b15307a34021e004a7f79b`，代表命令为 `PYTHONDONTWRITEBYTECODE=1 bash scripts/validate-skills`；Plan 读回 `match`。
- 候选外 Validate 修改已恢复，文件 SHA-256 `a6054e5128d6f92075ee94851d6ca7a9cd8dac274503e674062e191745039875`，与完整备份和原 diff 一致，扩展属性及原文件元数据保留。

## 未完成

- Task 返修已登记 done，validation/review 均为 pending；`pass@95f612b` 与其后只读复评的 P2 已保存于 a0968a3，旧通过不得用于后续批准。`fail@5c52bf8` 保存在 53179e6。Ship 未执行。
- 候选 `fba6705` 的独立 Validate 曾通过标准检查 233 项、Python 3.9 场景 59 项、Node 组件 131 项及受限浏览器点验；其后独立复评发现三个边界问题并已退回。该通过只适用于原候选。
- 原 14 次试次及 43 run 结果保留。B01 后续补充试次经历评审退回、局部修复、独立重验和 Review，机械 oracle 通过；仅规划样本与桌面候选补充样本的定向检查通过。桌面补充样本明确增加 T3 路线提示，原失败不被覆盖。真人样本仍无指定观察者的实际答复。
- SCN-07 联合反馈及处理、SCN-08 明确答复后续接、SCN-09 变化后的定向重验均已取得同机合成机制证据并经独立 Validate 判定符合；模拟输入不得冒充该用户真人答复。
- SCN-07 独立只读核对已完成：区分了 A1 通过、B1 失败、I 未运行与合成反馈身份，实际模型 `gpt-6.2-sol`；父上下文在夹具中分别登记 fail@C0。S0 `d9a5ae2509b7d2519a57c313f1573796d2325643` 仅增加状态和证据，业务与 C0 等价；唯一续写仓为 `continuation/runs/scn07-09-local/resume`。
- SCN-08 独立续接已找回原授权与答复并请求重开 B；主 Agent 实际将 B 从 done 重开，A 投影未变。B 返修候选 C1 为 `f79a684569486865e8eaae5f8f962f9df4ab0009`，仅删除一行业务配置；Build 的 B1 已经主 Agent 使用固定 argv 复核，Task done。
- SCN-09 独立上下文请求仅重验 B1；主 Agent 对 C1 实际运行并得到 exit 1、stdout/stderr 空，A1 的旧输入 blob 与判据未变。夹具 A、B 均按 I 缺证登记 fail@C1，证据与状态交接提交为 `15781e0ed499fd0fe85685bbc16f3da88f8fb5b3`，业务与 C1 等价；原真人答复仍缺失。
- 联合候选独立综合 Validate 任务 `b1db88c0-d68c-4eab-aab6-1026323c9cf7` 已完成，宿主实际模型 `gpt-6.2-sol`；权威 validation 已登记 pass@f62b6fe，登记期间暂置的候选外文件原 inode、内容、属性及 diff 均已恢复并读回。
- 正式独立 Review 已完成，`gpt-6.2-sol` 的 changes_requested 已由权威 CLI 登记：四项 P2 分别涉及检查点清理、面板场景列表、观察失败导致动作重复和桌面筛选身份；另有两项 P3。发现已保存至 `.sdlc-v1/evidence/FEAT-human-validation.review.md`，主 Agent 在隔离容器复现了三项运行后果。
- 目标工作树的 `skills/sdlc-validate/SKILL.md` 有归属未核实的未提交变更，用户选择保留在冻结候选之外；原 diff 与工作区副本一致。后续验证登记仍须满足非 SDLC 工作树干净的前提。
- 仓库提交约定要求同步 CHANGELOG；用户明确批准的本地候选仅限既定 40 路径，且方案将 CHANGELOG 排除于本地迭代。该候选按用户范围保留；后续获授权的提交或发布准备应检查并采用适用草稿。真实跨机授权取证、真人答复、完整盲测及真实发布未覆盖。

## 下一步

- `60240a9` 的独立复评发现拒绝证据重复读取、动作结果 getter 抛错及空诊断；退回已保存。返修 `5c52bf8` 的独立 Validate 为 `IMPLEMENTATION_FAILED`：普通推进和回看均会二次读取原生 `Error.message`，且诊断转换的副作用可能使拒绝后的状态检查误通过；Node 148 项、历史边界 22 项及 Chromium 面板和桌面检查通过。fail 已登记、读回并保存于 53179e6，重开 Task 清除了当前投影中的失败；候选外文件已原样恢复。
- 候选 `95f612b` 的验证通过及只读复评 P2 均已保留。主 Agent 返修仅使用已读取的错误信息或稳定兜底，避免动作日志及读取错误提示触发对象转换；组件 152 项、旧诊断 4 项、等待 8 项通过，旧动作证据 12/14、异常边界 13/14 的其余项通过。被排除的三项断言原先要求执行自定义转换，现由无副作用回归替代；原文件未改。固定候选后需独立 Validate 和 Review；详见 `.sdlc-v1/evidence/FEAT-human-validation.review.md`。
- 回填工程验证记录前核对 Plan 内容漂移、批准来源、写者独占及必要的批准型重记；不得以干净副本直接代替权威主仓状态。新增续验按用户新预算单独记录，不重复催问已有真人观察。

## 必要引用

- 原批准正文：/Users/mac/hansen_agent_team/workspace/20261119-sdlc-human-acceptance/approved-plan-preimage
- 旧 Plan 摘要及当前 Feature 身份：.sdlc-v1/state.json
- 范围和确认依据：../../workspace/20261120-sdlc-combined-acceptance/acceptance-preconditions.md
- 联合试次与用量：../../workspace/20261120-sdlc-combined-acceptance/trial-ledger.md
- 干净验证副本：../../workspace/20261120-sdlc-combined-acceptance/formal-validation-f62b6fe
- 独立验证与检查日志：../../workspace/20261120-sdlc-combined-acceptance/formal-validation-results/report.md
- 第二次独立续验与缺口：../../workspace/20261120-sdlc-combined-acceptance/continuation/formal-validation-f62b6fe-r2/report.md
- 试次比较与浏览器结果：../../workspace/20261120-sdlc-combined-acceptance/benchmark-summary.md 和 prototype-browser-results.md
- 变更原文快照：../../workspace/20261120-sdlc-combined-acceptance/concurrent-validate-change-0716.diff
- 验证登记及原文件恢复回执：../../workspace/20261120-sdlc-combined-acceptance/formal-validation-results/registration-attempt.jsonl
- 续验记录与诊断句柄：../../workspace/20261120-sdlc-combined-acceptance/continuation/recovery-log.md
- SCN-07–09 合成补证设计：../../workspace/20261120-sdlc-combined-acceptance/continuation/scn07-09-design.md
- 第三次独立 Validate：../../workspace/20261120-sdlc-combined-acceptance/continuation/formal-validation-f62b6fe-r3/report.md
- 通过登记守护及只读预检：../../workspace/20261120-sdlc-combined-acceptance/continuation/register_validation_pass_guard.py
- 权威通过登记与评审镜像回执：../../workspace/20261120-sdlc-combined-acceptance/continuation/formal-validation-f62b6fe-r3/pass-registration.jsonl、review-mirror.jsonl
- Review 发现：.sdlc-v1/evidence/FEAT-human-validation.review.md；拒绝登记守护：../../workspace/20261120-sdlc-combined-acceptance/continuation/register_review_rejection_guard.py
- 返修 Plan 预核准映射：../../workspace/20261120-sdlc-combined-acceptance/continuation/repair-plan-approval.json
- 返修定向检查与失败原始记录：../../workspace/20261120-sdlc-combined-acceptance/continuation/repair-node-{red,target}.json、repair-python-{red,target}.json
- 返修隔离快照及完整检查：../../workspace/20261120-sdlc-combined-acceptance/continuation/repair-build-check-xv6zmn18/
- 独立验证与 Review 登记回执：../../workspace/20261120-sdlc-combined-acceptance/continuation/repair-validation-fba6705/；Review 登记守护：../../workspace/20261120-sdlc-combined-acceptance/continuation/register_review_fba6705_guard.py
- 独立失败及登记回执：../../workspace/20261120-sdlc-combined-acceptance/continuation/repair-validation-5c6c92c/；本轮反例、Node、Chromium 日志：同目录上层 `repair-action-boundary-{red,target,prior-fixed,node-final,browser}.log`
