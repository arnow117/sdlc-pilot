# Spec: backlog review 看板（需求树双表征 + 实时对话编辑）

> Date: 2026-06-16
> Status: draft
> Target surface(s): backlog 工具（skills/sdlc-backlog + scripts/backlog.py）+ 生成的网页（前端可见面）
> Active roles (anticipated): design, skill-maintainer, qa
> Validate modes (anticipated): correctness, e2e:Web

## 1. 问题 / 目标

`.sdlc/requirements/` 需求树目前只有**机器视角**的散切片（`readyqueue`/`coverage` 输出 JSON），没有：
1. **整棵树**的结构化导出（agent 想一次拿到全貌得自己 walk 文件）；
2. **人看的视图**——领域→子域→需求条目的层级、每条的实现状态，一眼看不到；
3. **review gate**——没有一个让人在推进前检查/补全需求树的关卡（backlog 一直缺这道闸）。

目标：给 `backlog.py` 加两个只读导出命令（整树 JSON + 看板 HTML），HTML 复用 web-review 的 Live mode，
让人在网页上**选中某片需求叶 → 对话式追问 / 完善上下文 / 移动到另一个域**，由正在跑 SDLC 的 agent 落地修改。
= 给 backlog 补上人看 + 可编辑的 review gate。

## 2. 非目标（YAGNI）

- ❌ **不**内置独立 AI 服务/LLM 后端（chatbot = 现有 agent 经 Live mode 驱动，见 §4 方案 A）。
- ❌ **不**做"从工程代码分析自动生成需求树"——那是独立的下一个特性（backlog Seed 升级），本特性只手搓/快生成一棵小示例树用于测试。
- ❌ **不**做自由聊天流单框；右侧沿用 web-review 的**按叶意见线程**模型（复用 > 新建）。
- ❌ **不**新增顶层 skill、**不**新增 stage；新命令挂 `backlog.py` + `sdlc-backlog` SKILL 的 op。
- ❌ **不**让渲染器写树——渲染只读；树的修改由 agent（单写者）经 Edit / `backlog.py move` 完成。

## 3. 现状摘要（Explore 产出）

- **代码**：`scripts/backlog.py`（纯标准库）已有 `parse_frontmatter`/`load_leaves`（产出含 10 字段 + `_path`/`_depth` 的叶 list）+ `readyqueue`/`coverage`（JSON）/`lint`/`retire`。无整树 JSON、无 HTML、无 leaf 移动 op。
- **复用资产**：`skills/sdlc/references/web-review/` 有 `annotate.css`/`annotate.js`（注入任意 HTML 的划词意见层）+ `server.py`（`/wait` 长轮询、`POST /feedback`、`/rev` 刷新戳、`/replies.json` 回复回灌）+ `test_live.py`。playbook §2/§3.3 明确支持"手工可视化页 + 注入两行 + 套 server.py"。
- **状态机**：叶 `status`: captured→spec'd→planned→built→validated→shipped；`priority` P0-P3；`risk_level` low/medium/high。
- **测试**：`scripts/test_backlog.py` 存在（含 RetireTest）。需补 tree/board/move 用例。
- **缺口**：本仓自身无真实 `.sdlc/requirements/` 树 → e2e 需先建 fixture。

## 4. 方案与决策

**方案 A（选定）：网页当 agent 的眼睛和手。** 右侧"chatbot" = 正在跑 SDLC 的 agent（Claude/Codex），
经 web-review **Live mode** 双向通道驱动；不引独立 AI 后端。

- 被否 **方案 B**（网页内置独立 LLM 服务）：破"纯文件 + agent 当引擎 + 可移植"三铁律，工作量大，本质是独立产品，不属 sdlc-pilot。
- 被否 **collect-only 纯被动批注**：用户要的是对话直接改树，不是只收集意见。Live mode 让 agent 当场处理，正好满足，且 agent 是单写者（不违律）。

**范围姿态（§2.4b）**：**EXPAND** — 交互从"静态渲染"扩展为"实时对话编辑"，因为这是 backlog review gate 的核心价值；但严格 EXCLUDE 自动生成器（独立特性）与独立 AI 服务（方案 B），防爆量。

## 5. 设计

### 5.1 命令面（挂 `backlog.py`，与 readyqueue/coverage/lint 同构）

| 子命令 | 行为 | 写树? |
|--------|------|-------|
| `tree --root <root>` | 复用 `load_leaves` → 按 `domain_path` 嵌套 → 整树 JSON 到 stdout | 否（只读） |
| `board --root <root> [--out <path>]` | 渲染自包含 HTML（注入 annotate 两行）到文件（默认 `<root>/_board.html`） | 否（只读） |
| `move --root <root> --leaf <id> --to <domain>/<subdomain>` | 叶迁域：mv 文件 + 改 `id`/`domain_path` + **改写全树指向旧 id 的 `depends_on`** | **是**（确定性机械写，仿 retire） |

`board` 内部调与 `tree` 同一份 `build_tree(leaves)`（DRY）。`move` 是 backlog.py 第 2 个写树 op（retire 之后）。

### 5.2 整树 JSON 形状（`tree` 输出 / 也是 `board` 的渲染输入）

```json
{ "domains": [ { "domain": "<name>", "meta": { /* _domain.md frontmatter */ },
    "subdomains": [ { "subdomain": "<name>", "meta": { /* _subdomain.md */ },
        "leaves": [ { "id","title","status","priority","risk_level",
                      "depends_on","old_system_ref","new_domain_path","cross_link" } ] } ] } ],
  "summary": { "total": N, "by_status": { "...": n }, "ready_count": M } }
```

### 5.3 HTML 看板（左树 + 右意见线程）

- **自包含单文件**：内联 CSS+JS（含聊天面板），纯标准库字符串拼装（无模板引擎/网络字体 → 可移植、离线可开）。视觉遵 `DESIGN.md`。仅依赖 `server.py` 同目录托管（不依赖 annotate.css/js）。
- **布局：左树 + 右侧常驻聊天栏**（桌面 flex 分栏；<768 聊天收为底部抽屉/切换）。
- **左：三级折叠树**：原生 `<details>/<summary>` 嵌 domain→subdomain→leaf；叶卡显示 id/title/status 徽章/priority/risk/deps；顶部每 domain 一条 coverage burndown 条。**点叶卡 = 选中**（高亮 `aria-current`），右侧切到该叶的聊天线程。
- **右：聊天面板（chatbot，新建，替代批注层）**：头部显示选中叶 id+title；消息区按 `你/agent` 气泡呈现该叶对话；底部输入框 + 发送。换一片叶切到它自己的线程（per-leaf 会话）。
- **实时回路（复用 web-review Live mode + server.py，不改后端）**：
  - 发送：chat.js `POST /feedback`，body `{id:<msg-id>, leaf:<leaf-id>, message:<文本>}`（server.py 接任意 JSON，写 feedback.json + 追 feedback-history.jsonl + 唤醒 /wait）。
  - agent：前台阻塞 `curl /wait` 拿到消息 → 按意图处理：**追问**=读叶答疑；**完善上下文**=Edit 叶 `.md`；**移到另一个域**=跑 `backlog.py move`。
  - 回灌：agent 把回复写进 serve 目录的 `replies.json`（`{<msg-id>: 回复文本}`）+ bump `rev`。
  - 页面：轮询 `/replies.json` 追加 agent 气泡；轮询 `/rev`，树被改（move/edit）则 reload。线程持久化 = 页面加载时读 `/feedback-history.jsonl`（所有用户消息，按 leaf 分组）+ `/replies.json`（按 msg-id 配对）重建，刷新不丢。
- **降级**：无浏览器/curl → 退回文件式（agent 读 `feedback.json`/`feedback-history.jsonl` 处理、写 `replies.json`），再不行 text_mode。

### 5.4 错误处理

- `tree`/`board` 遇空树或 root 不存在：沿用现有 `cmd_*` 的 `root 不存在` 非 0 退出；空树渲染出"暂无需求"占位页（不崩）。
- `move`：目标域不存在 → 报错非 0、不动文件；旧 id 无叶引用 → 正常；**幂等**：目标已存在同 id → 拒绝覆盖（仿 retire）。
- Live mode 处理时匹配不到 `quote` → 回报该条请用户澄清，**不臆改**（沿用 playbook §3.6）。

### 5.5 测试策略

- **correctness（build TDD）**：`test_backlog.py` 加 `tree`（嵌套正确/叶全/summary 计数）、`board`（含每叶 id、annotate 两行已注入、html 骨架合法、空树占位）、`move`（迁域后 id/path/domain_path 一致 + depends_on 全树改写 + 幂等拒覆盖）。
- **e2e:Web（validate）**：建 fixture 小树（≥2 domain、含 depends_on、覆盖多种 status）→ `board` 渲染 → 浏览器验：三级折叠、状态徽章、coverage 条、断点（768）、annotate 层加载、`/wait`→提交→`/rev`刷新闭环（用 `test_live.py` 既有回归兜底）。
- **skill-maintainer（R10）**：`bash scripts/validate-skills` PASS + 按 §7b 文档同步。

## 6. 怎么算 done（前置验收）

- [ ] `python3 scripts/backlog.py tree --root <fixture>` 输出 §5.2 形状、嵌套与计数正确。
- [ ] `python3 scripts/backlog.py board --root <fixture>` 产自包含 HTML：左树三级折叠 + 状态/优先级徽章 + coverage 条；annotate 两行已注入；空树不崩。
- [ ] `python3 scripts/backlog.py move --root <fixture> --leaf <id> --to <d>/<s>` 正确迁域并改写依赖，幂等拒覆盖。
- [ ] fixture 树起 `server.py` + 开页：选叶提交请求 → agent 经 `/wait` 收到 → 改树/答疑 → `/rev` 刷新可见。
- [ ] `python3 scripts/test_backlog.py` 全绿（含新用例）；`bash scripts/validate-skills` PASS。
- [ ] 视觉与交互态符合 `DESIGN.md`（含 a11y/响应式/reduced-motion）。

## 7. Eval 契约（仅 AI/模型/策略工作；否则 N/A）

N/A — 本特性不触及 AI/模型/策略/prompt/evals 面。

## 7b. 设计契约（UI/前端工作）

见 `<repo-root>/DESIGN.md`（本特性新建）。定义：风格方向（暖色编辑感 + 硬投影）、色板 token（奶油/鼠尾草绿 + status/priority 语义色）、字体/8px 间距、组件（折叠树/叶卡/徽章/coverage 条/意见线程）、交互态（hover/focus-visible/选中叶）、a11y（对比 AA / 原生 details 键盘 / reduced-motion）、响应式（768 分栏↔单列）。本特性首次建立 sdlc-pilot 的 DESIGN.md。

## 8. Deferred Ideas（结构化延后）

- **从工程分析自动生成需求树**
  - Why：手搓需求树费力；从已有项目的技术架构/数据结构/对外接口反推，能快速 bootstrap 一棵真实树，且产物正好喂给本看板形成闭环。
  - Trigger：本看板特性 ship 后，作为下一个特性单独走完整 SDLC。
  - Breadcrumbs：归 `sdlc-backlog` 的 Seed 操作升级（SKILL.md §2）；可参考 `sdlc-onboard` 的 surface-map 测绘逻辑作为分析输入；本特性的 fixture 树即它的早期手工版。
- **方案 B：独立 AI 看板应用**
  - Why：若要做成可独立运行、带自有 AI 后端的产品。
  - Trigger：明确要做对外产品时（届时应另起项目，不在 sdlc-pilot 内）。
  - Breadcrumbs：本 spec §4 已记被否理由（破三铁律）。
- ~~真自由聊天流单框~~ **（已采纳，不再 Deferred）**：board v1 演示后用户反馈批注式不是想要的 chatbot，遂在本特性内升级为右侧常驻**聊天面板**（per-leaf 会话气泡 + 输入框 + 叶详情），替代 annotate 批注层。见 §5.3。
- **backlog 管家 daemon（+ 可选 MCP 工具层）—— 实时自动应答**
  - Why：当前 chatbot 需 agent 在场处理消息（不前台挂 `/wait` 就不自动回）；要真·实时自动应答，需一个常驻 daemon 循环 `curl /wait` → 喂 headless Claude（读 `.sdlc/PROFILE`+树+CLAUDE.md bootstrap context）→ 改树/答疑 → 写 replies/bump rev。
  - 为何不在本特性做：= 被否的"方案 B（独立 AI 后端）"，破 sdlc-pilot 三铁律（纯文件/agent 当引擎/可移植）。应作**独立伴生项目**，把 `backlog.py` + `.sdlc/` 当底座/库。
  - Trigger：要"无人值守的 backlog 管家"时单独立项；可叠一层 MCP 把 `tree/board/move/edit/pending` 包成工具供该 daemon（或 Claude Desktop）调。
  - Breadcrumbs：context handoff 载体已就绪（`.sdlc/PROFILE.md` + 需求树 + `CLAUDE.md`）；Live 后端 `server.py` 的 `/wait` 长轮询即 daemon 的消息入口。

## 9. Canonical refs（强制累积）

- `scripts/backlog.py`（扩展目标：tree/board/move + 复用 load_leaves/parse_frontmatter）
- `scripts/test_backlog.py`（加用例）
- `skills/sdlc-backlog/SKILL.md`（加 op 章节 + 顶部 op 枚举）
- `skills/sdlc/references/web-review/{annotate.css,annotate.js,server.py,playbook.md,test_live.py}`（复用）
- `<repo-root>/DESIGN.md`（本特性新建）
- `~/Downloads/requirement-dashboard.html`（配色参考）
- `CLAUDE.md` 迭代表「加/改 backlog 派生操作」（同步指引）：① backlog.py + test → ② SKILL.md op 章节 + 枚举 → ③ 若涉生命周期则 driver/STATE（本特性不涉，move/tree/board 非生命周期 op）→ ④ validate-skills
