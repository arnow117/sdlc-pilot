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

## 返修的独立验证

- 候选 `fba6705fdd2589bb12c1b647ecb4ffa4c6856664` 的四项 P2 和两项 P3 返修由独立执行者验证为 PASS；宿主回执 `codex / gpt-6.2-sol / xhigh`，`executedModel=gpt-6.2-sol`。
- 实际运行的 `bash scripts/validate-skills` 退出 0、233 项通过；Python 3.9 场景 59 项和 Node 组件 131 项均通过。受限 Chromium 点验覆盖面板无效项隔离与工单按角色筛选。浏览器首轮路径错误未启动，修正后退出 0；[完整报告与原始日志](../../../../workspace/20261120-sdlc-combined-acceptance/continuation/repair-validation-fba6705/validation/report.md)。
- SCN-07–09 仅有同机合成机制证据；原 B01 真人答复、共同 I、跨机器与真实发布仍未覆盖。独立 Review 为下一阶段。

## fba6705 的独立复评

- 结论 `changes_requested`；执行者请求 `codex/gpt-6.2-sol/xhigh`，宿主确认 `executedModel=gpt-6.2-sol`。[独立复评原文](t3-thread://v2/cb0ab126-b88e-4134-8282-a4e59f62c293/thread:delegated-task:command%3Amcp%3Aa919fc85-eb27-47f2-b212-4d7af9bab58a%3Adelegate-task%3A1f4db8eb-98e6-49b4-9c4a-08c6f52df0bd)。
- **P2 · violates**：场景数组的稀疏空位、抛异常的 id getter、与无效项重复 id 三条路径仍会阻断合法场景的面板挂载或启动；列表与启动需采用一致的识别规则。
- **P2 · violates**：观察值序列化预检与失败写入分别调用可变化的 `toJSON()`，第二次抛错时动作仍会重复执行，回看状态也未收束；需一次取得安全证据并覆盖普通推进与回看。
- **P2 · violates**：`pending` 的读取在回执到达前返回 `undefined` 时，原等待语义被新校验提前判为失败；轮询、手动确认与回看均需恢复等待，同时保留读取错误和不可序列化值的失败处理。
- 检查点清理、历史 pending 评审反例、桌面身份筛选及本机布局下三条证据链接已由复评核查；历史失败及未覆盖项仍保留。

## 5c6c92c 的独立验证

- 结论 `IMPLEMENTATION_FAILED`；宿主实际执行模型 `gpt-6.2-sol`。原 139 项 Node 通过，额外边界 6 项通过、2 项失败；受限 Chromium 的普通隔离路径通过、异常对象反例失败。[报告与原始日志](../../../../workspace/20261120-sdlc-combined-acceptance/continuation/repair-validation-5c6c92c/report.md)。
- 数组项或 `read()` 抛出无原型对象时，`readErrorParts` 的字符串转换再次抛错：真实面板无法挂载，或普通推进重复动作、回看仍停留 running。实际读取错误的格式化必须有安全退路；待修复后重验。
- 现有异步等待、正常读取异常、变化的 `toJSON()`、适配器参数与对象比较已按报告通过；先前失败和未覆盖项继续保留。

## 60240a9 的独立复验

- 结论 `PASS`；执行者请求 `codex/gpt-6.2-sol/xhigh`，宿主确认 `executedModel=gpt-6.2-sol`。三个组件套件 143 项、上一轮边界脚本 8 项、本轮独立边界 14 项通过；Chromium 六组异常场景及桌面筛选通过。[完整报告与原始日志](../../../../workspace/20261120-sdlc-combined-acceptance/continuation/repair-validation-60240a9/report.md)。
- 原标准检查 233 项沿用 fba6705 的独立执行记录，报告核对了相关输入依赖；原执行版本不变。B01 真人答复、共同 I、跨机器交割及真实发布仍未覆盖。

## 60240a9 的独立复评

- 结论 `changes_requested`；宿主确认执行模型 `gpt-6.2-sol`。[复评原文](t3-thread://v2/cb0ab126-b88e-4134-8282-a4e59f62c293/thread:delegated-task:command%3Amcp%3Aa919fc85-eb27-47f2-b212-4d7af9bab58a%3Adelegate-task%3A234eed29-1582-4c18-a709-e9dc6528f205)。
- **P2 · violates**：诊断转换与拒绝证据分别多次读取产品错误，可能伪造或丢失拒绝证据；普通推进和回看需使用同一次证据读取。
- **P2 · violates**：动作结果的 `error` getter 抛错时在失败记录之前退出，导致动作重复或回看停留 running；读取动作结果需纳入失败收束。
- **P2 · violates**：异常对象的字符串转换返回空值时，无效场景被面板当成有效默认项；无效摘要必须保留非空诊断。

## 95f612b 的独立只读复评

- 状态 `incomplete`：候选外 Validate 技能的未提交改动使 Review 的工作树前提未满足；尚无正式 Review 决定。宿主确认执行模型 `gpt-6.2-sol`。[原生复评及定向探针](t3-thread://v2/cb0ab126-b88e-4134-8282-a4e59f62c293/thread:delegated-task:command%3Amcp%3Aa919fc85-eb27-47f2-b212-4d7af9bab58a%3Adelegate-task%3Asdlc-human-validation-95f612b-independent-review-20261121)。
- **P2 · violates**：回看拒绝动作后先观察到 `changed`，追加日志时对错误对象做字符串转换，将产品值改成 `unchanged`，下一观察步误通过；原版对照保持 `changed` 并失败。应只用已捕获的消息、代码或稳定兜底构造动作日志，在普通推进与回看验证跨步骤产品状态不被日志改变。
- **P3 · 建议**：普通推进和回看分别构造同形日志；可在修复时消除有实际后果的重复，但不以单纯减少代码行数作为验收条件。原 `pass@95f612b` 和单步验证证据按其实际覆盖保留，不再用于后续批准。

## 2b1cee5 的独立复评

- 结论 `approved`，未发现阻塞项；执行者与宿主实际模型均为 `codex/gpt-6.2-sol`，推理强度 `xhigh`。[子线程评审原文](t3-thread://v2/cb0ab126-b88e-4134-8282-a4e59f62c293/thread:delegated-task:command%3Amcp%3Aa919fc85-eb27-47f2-b212-4d7af9bab58a%3Adelegate-task%3Asdlc-human-validation-2b1cee5-independent-child-review-20261121)。
- **preserves**：上轮跨步骤误通过已修复。普通推进和回看从已捕获的拒绝证据生成诊断；已验证第一步拒绝后第二步仍读取实际 `changed` 状态，诊断不执行产品对象转换，失败动作不重复。无证据支持的新重复实现或可避免工程债未发现。
- 复用独立 Validate 的 152 项组件检查、37 项适用旧探针与 Chromium 面板证据，三个要求对象转换的旧断言按报告过滤。[验证报告](../../../../workspace/20261120-sdlc-combined-acceptance/continuation/repair-validation-2b1cee5/report.md)。B01 真人答复、共同 I、跨机器交割与真实发布均未覆盖，不外推为已完成。

## v8.0.0 发布候选的独立验证

- 候选 `4869345cd7feec0a9730a72635afc78b51d63d51` 为 `2b1cee5` 加两份插件版本元数据与 CHANGELOG，三个版本均为 `8.0.0`。独立执行者 `codex/gpt-6.2-sol/xhigh` 的标准检查退出 0、233 项通过，既有行为证据按输入适用范围复用。[验证报告](../../../../workspace/20261120-sdlc-combined-acceptance/continuation/release-8.0.0-validation/report.md)。
- 首轮因执行环境额外设置 `GIT_NO_REPLACE_OBJECTS` 导致检查拒绝；移除该设置后的同候选重跑通过。发布和实际分发 smoke 尚待执行。

## v8.0.0 发布差异的独立复评

- 候选 `4869345cd7feec0a9730a72635afc78b51d63d51` 的复评结论为 `approved`，未发现必须修复项。宿主实际执行模型为 `gpt-6.2-sol/xhigh`；评审核对了三处版本、CHANGELOG、兼容说明、与前一已审业务源码的差异及本候选验证证据。[子线程评审](t3-thread://v2/cb0ab126-b88e-4134-8282-a4e59f62c293/thread:delegated-task:command%3Amcp%3Aa919fc85-eb27-47f2-b212-4d7af9bab58a%3Adelegate-task%3Asdlc-v8-4869345-independent-review-20261121)。
- **P3 · violates**：发布说明草稿的验证状态仍为待执行；主 Agent 在发布前将 233 项候选检查及旧业务证据的版本分别标明，实际分发与发布后检查不得提前记为通过。

## v8.0.0 发布预检

- 用户已授权发布新版。操作标识 `FEAT-human-validation-v8.0.0-20261121`；目标为公开仓库 `arnow117/sdlc-pilot` 的默认分支和 GitHub Release。发布候选、验证 commit、拟创建标签 `v8.0.0` 的目标均为 `4869345cd7feec0a9730a72635afc78b51d63d51`。
- 外部动作前读回：远端 `main` 为 `e587eb1a2abf6ca40b3f0b790f902f3c64e349c6`；上一正式 Release 为 `v7.3.0`，标签所指 commit 为 `3d8c7903b7fa23bc9743d930f194b4fb114f97fc`；远端尚无 `v8.0.0` 标签或 Release。发布说明 SHA-256 为 `6cfa4cb7a145ca3af999a438e02d77b0ef3369c4978faa73f98e6974f1ba8048`。
- 预期依次为更新 `main` 和创建指向验证候选的标签、创建公开 Release、从该 Release 下载源码进行版本及行为 smoke、核对默认分支安装入口，再登记实际发布。中断时先查询 `https://api.github.com/repos/arnow117/sdlc-pilot/git/ref/heads/main`、`https://api.github.com/repos/arnow117/sdlc-pilot/git/ref/tags/v8.0.0` 和 `https://api.github.com/repos/arnow117/sdlc-pilot/releases/tags/v8.0.0`，核对回执与目标，不盲目重发。若需恢复，保留现场并以 `v7.3.0` 为 last-good；使用正常的前向修复或经授权的回退，不强推或重写历史。
