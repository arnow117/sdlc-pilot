# web-review —— 划词批注式文档复核(可选 gate 机制)

> distilled-from: session:spec-web-review-2026-06-10
>
> 这份 playbook 是 **数据,不是 skill**(与 `evolve-loop.md` / `divergence-frames.md` 并列)。
> 任何引擎(Claude + Read/Edit/Bash,或 Codex)都能照着跑;批注层/服务器是同目录的 **工具资产**(命令即交付物,保留)。
> 由 `sdlc-spec` / `sdlc-plan` 的**用户复核 gate** 作为**可选**升级形态引用——文档长/结构复杂、聊天里逐条批太累时用;简单文档直接 text_mode 聊天批更快。

---

## 0. 它解决什么

spec/plan 的复核 gate 默认在对话里逐条过。文档一长,这种方式低效、易漏。
web-review 把任意 markdown 渲染成**可在浏览器划词加批注**的页:用户选中任意文字→写评论→高亮+面板累积→选「通过/要改」→一键提交;本地服务器把批注回收成 `feedback.json`,**agent 读取后把所有批注统一改回源文档**。

**不替代** gate 的判定权——它只是把"用户怎么把意见喂回来"从手敲升级为划词批注。approve/要改的最终前进与否,仍由对应 stage skill 的 gate 决定。

## 1. 何时用(门控,默认不用)

- 文档长 / 结构复杂(多节、多表、跨域契约),聊天逐条对太累 → 提议 web-review。
- 用户明确要"网页上标注 / 生成网页我看看 / 划词批注"。
- 否则:**默认走 text_mode 聊天批**(更快、零进程)。

## 2. 工具资产(同目录)

| 文件 | 职责 |
|------|------|
| `build.py` | `md → 可批注审阅页`(零依赖 md 子集渲染 + 注入批注层 + 复制 server)|
| `annotate.js` `annotate.css` | 通用划词批注层(选词→评论→高亮→右侧面板→POST 提交);注入任意 HTML 通用 |
| `server.py` | 零依赖 localhost 回收服务器:托管页面 + `POST /feedback` 写 `feedback.json` |

> 也可不用 `build.py` 的通用渲染,而手工写更精美的可视化页——只要 `</head>` 前注入 `annotate.css`、`</body>` 前注入 `annotate.js`,并和 `server.py` 同目录托管即可。批注层对任意页面通用。

## 3. 流程(原则,非命令手册)

1. **定源**:默认 `<repo>/.sdlc/spec.md`(spec gate)或 `plan.md`(plan gate);或用户指定 md / 已有可视化 HTML。
2. **生成到 tmp**:产物落临时目录(约定 `${TMPDIR:-/tmp}/sdlc-web-review-<slug>/`),**不污染目标仓**。
3. **构建**:跑 `build.py <源.md> <outdir> --title "<标题>"`(它会渲染 + 注入批注层 + 把 `server.py` 复制进 outdir)。手工可视化页则改名 index.html、注入两行、把 `server.py` 拷进去。
4. **起服开页**:在 outdir 起 `server.py`(后台常驻,绑 `127.0.0.1`),浏览器开 `http://127.0.0.1:<port>/`。起服前先清占用端口。
5. **告诉用户怎么标**:选中文字→「💬 添加评论」→写评论→保存;右侧面板可删可定位;选「通过/要改」→「提交反馈给 agent」;提交后回对话说一声。
6. **回收 + 统一改**:读 `<outdir>/feedback.json`——
   - 结构:`{ verdict:"approve"|"changes", count, annotations:[{section, quote, comment}] }`。
   - 对每条 annotation:按 `section` 缩小范围、在源 md 里定位 `quote`,按 `comment` 意图改;**一次性 consolidated pass** 改完再向用户汇总改了哪些。匹配不到的 quote → 回报该条请用户澄清,**不臆改**。
   - 必要时重跑 build 让用户再看一轮。
7. **回判 gate**:`verdict=approve` 且无阻断批注 → 该 stage 的 gate 通过(spec → `Status: approved` 并写回 STATE;plan → 定稿)。`changes` → 改完重跑该 stage 的自检,再回 gate。
8. **收尾**:停服务器;tmp 产物可留可清。

## 4. 约束

- **localhost-only**:服务器绑 `127.0.0.1`,不出网;批注全在本地。
- **可移植**:仅 `python3` 标准库;无 Task / 无 AskUserQuestion 依赖。无浏览器的环境(纯 Codex)→ 降级:把 `feedback.json` 让用户手填,或直接 text_mode 聊天批。
- **md 子集**:`build.py` 支持标题/段落/有序无序列表/GFM 表格/围栏代码/引用/行内 code/**粗体**/链接,足够 spec/plan;复杂排版走手工可视化页。
- **不改 gate 语义**:web-review 是复核**机制**的可选项,不改"批准前不前进"的纪律。
- **定位健壮**:统一改时按 `section`+`quote` 精确匹配;匹配不到不臆改,回报澄清。

## 5. feedback.json 示例

```json
{
  "doc": "骨架 Spec 审阅",
  "verdict": "changes",
  "count": 2,
  "annotations": [
    {"id":"a1","section":"5. 设计","quote":"18 个实体","comment":"漏了营销券实体,补一个 Coupon"},
    {"id":"a2","section":"6. 怎么算 done","quote":"两笔并发 hold","comment":"再加一个 consent 撤销的验收场景"}
  ]
}
```
