# Validate 汇总 — backlog review 看板

> 日期: 2026-06-16 ｜ 分支: feat/backlog-review-board ｜ modes: correctness + e2e:Web
> 阶段总判定: **PASS**

## correctness — PASS

| 检查 | 命令 | 结果 |
|------|------|------|
| 单元/集成套件 | `python3 scripts/test_backlog.py` | Ran 19 tests, OK, exit 0 |
| 结构 lint | `bash scripts/validate-skills` | RESULT: PASS ✅ exit 0 |

新增覆盖：TreeTest(2) / MoveTest(3) / BoardTest(2)，含错误/边界路径（空树、拒覆盖、源叶不存在）。

## e2e:Web — PASS

**装置**：`backlog.py board` 渲染 `examples/requirements-fixture`（3 domain/6 叶）→ 服务目录（index.html + web-review annotate.css/js/server.py + rev）→ `server.py` 绑 127.0.0.1:8779。

| 端点 | 结果 |
|------|------|
| `GET /`（index.html） | HTTP 200 |
| `GET /rev`（Live 自刷新轮询） | HTTP 200，返回 "1" |
| `GET /annotate.css` | HTTP 200 |

**浏览器旅程（Playwright/chrome-devtools，1440 + 390 两断点截图）**：

- [x] 三级折叠树 domain→subdomain→leaf（原生 `<details>` 展开/折叠）
- [x] status 徽章配色遵 DESIGN.md：shipped=鼠尾草绿 / built=橙 / spec'd=蓝 / captured=灰
- [x] priority pill：P0 红 / P1 橙 / P2 黄 / P3 灰；risk 圆点
- [x] 每 domain coverage burndown 进度条（order 1/2、user 1/2、billing 0/2 shipped）
- [x] 依赖关系显示（"依赖: order.checkout.cart" 等）
- [x] 768 断点响应式：1440 桌面分栏；390 移动 coverage 卡片堆叠单列、叶卡满宽
- [x] 暖奶油底 + 奶油纸面 + 硬投影，整体符合 DESIGN.md「暖色编辑感」

### chat 面板复跑（设计变更后：批注层 → 右侧聊天 chatbot）
用户在 board v1 演示后反馈"批注不是想要的 chatbot" → 回 spec/build 升级为右侧常驻聊天面板（spec §5.3 + DESIGN §4 已改）。复跑 e2e:Web：
- [x] 布局：左树 + 右侧常驻聊天栏（桌面分栏；移动底部抽屉）
- [x] 点叶=选中（aria-current 高亮）+ 右侧头部切到该叶
- [x] **对话回路端到端通过**：选中 `billing.pay.refund` → 发送"验收标准是什么？" → `POST /feedback`（feedback.json + history 收到）→ agent 写 `replies.json` → 页面 3s 轮询追加 agent 气泡（user 右绿气泡 / agent 左奶油气泡），无需刷新
- [x] Live 后端复用 server.py（/feedback /wait /rev /replies.json），未改后端、不依赖 annotate.*

### 叶详情面板 + live move 补测（用户反馈"看不明白叶子结构"+"没测完"后）
- [x] **叶详情面板**：点叶 → 右侧顶部显示完整字段（status/priority/risk 徽章 + 域/old/依赖）+ 正文（需求描述/验收/老系统）；数据经 `leaf-data` JSON 嵌入（`</`转义防注入）。截图验证 `billing.pay.refund` 详情正确。
- [x] **live move 端到端**：临时树副本上 `move billing.pay.refund → order/checkout` → 重渲染 + bump rev → 页面 2s 内自动 reload → `order.checkout.refund` 出现在 order/checkout、coverage 更新（order 1/3、billing 0/1）。证明"对话改树→页面刷新"通。
- 测试数：20（+TreeTest 2/MoveTest 3/BoardTest 3 + 既有 12）。

**console**：仅 2 条 benign —— `/replies.json` 轮询 404×10（无 agent 回复时的预期稳态，annotate.js `.catch` 处理）+ 表单字段 a11y issue（web-review annotate 的 textarea，非本特性代码）。无本特性引入的错误。

## 出口门控
- [x] 模式选齐（correctness + e2e:Web 全跑）
- [x] correctness PASS（19 测试 exit 0 + validate-skills PASS）
- [x] e2e:Web PASS（旅程到终态 + 双断点截图取证）
- [x] 无偷改实现（validate 期间未改实现文件；bug=0 无 escalate）
- [x] 证据完整（命令 + exit code + 截图）

→ validate 阶段 **PASS**，可进 sdlc-review。
