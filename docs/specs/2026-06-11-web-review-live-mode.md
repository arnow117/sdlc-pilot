# 设计:web-review Live Mode (notify) —— 把单向复核升级成实时双向

> Date: 2026-06-11
> Status: approved
> 形态结论:**不新增顶层 skill / 不新增资产**。扩 `references/web-review/playbook.md` 一节「Live mode (notify)」+ build.py 模板加 ~6 行自动刷新 poller。
> 上游:`references/web-review/playbook.md`(现有可选复核 gate);消费方 `sdlc-spec` / `sdlc-plan` 的用户复核 gate。

---

## 1. 问题 / 目标

现有 web-review 三件套(`build.py` 渲染可批注页 + `annotate.js/css` 批注层 + `server.py` 收 `feedback.json`)是**一次性单向**的:用户在网页划词批注、提交后,必须**回对话里手动说一声**,agent 才去读 `feedback.json`。这个"手动 signal"是整条复核回路里唯一需要人肉接力的断点。

目标:把它升级成**真双向实时**——agent 前台阻塞在一个 `curl /wait` 上,用户在网页提交的瞬间 server 释放该请求、把批注直接回给 agent,形成 `present → await → revise → present` 的 human-on-the-loop gate 循环。改完页面**自动刷新**到新版,用户全程只在浏览器里读+划词,无需切回对话发信号。机制只用"前台阻塞 shell"这个通用原语,**CC / Codex 等任意引擎都实时**(铁律 #2)。

## 2. 非目标(YAGNI)

- 不开 MCP server(C 方案胜出:前台阻塞 shell + HTTP 长轮询,跨引擎可移植,无 harness 特性依赖)。
- 不做通用"session 问任何问题"的 web 通道(复核是唯一消费者;未来要再抽象)。
- 不改 `annotate.js/css`、不改 `build.py` 的渲染逻辑(仅注入刷新 poller)。`server.py` 仅加 `/wait` 长轮询端点 + 换多线程,**不改现有 `/feedback` 语义**。
- 不替代 text_mode 聊天批(地板),也不替代现有文件式 web-review。
- 不新增顶层 skill(铁律 #1 保住)。

## 3. 关键认知(决定设计形态)

### 3.1 notify 原语 = 前台阻塞 `curl /wait`(HTTP 长轮询)——通用 shell 原语
**关键认知**:`run_in_background` 的"退出即唤醒"是 Claude Code harness 特性(Codex 无),不能用。但"agent 等到用户提交"有个**所有引擎都有的原语**:**前台 shell 调用本身阻塞到命令返回**(跑命令→等结束→拿 stdout)。

实现:agent 前台 `curl http://127.0.0.1:PORT/wait`;`server.py` 把这个 GET **挂起不回**(`threading.Event.wait`,零 CPU);用户 `POST /feedback` 时 server `event.set()` → 挂起的 `/wait` **瞬间释放**、把批注 JSON 回给 curl。无任何轮询、事件驱动、用户提交的精确时刻才返回。单次 exec 有上限(CC 10min)→ `/wait` 设 540s 超时,无人提交则回 204,agent **re-arm**(再 curl 一次)。用户快提交=1 次调用即时返回;拖 25min≈3 次调用,**不是每秒轮询**。

### 3.2 notify 是跨引擎地板,不是 CC 专属(铁律 #2 满足)
因为机制只是"前台跑一个阻塞 shell 命令(`curl`)",**CC / Codex / 任意有 shell exec 的引擎都吃**——present→await→revise→present 整条循环在 Codex 上同样实时。不再依赖任何 harness 特性。

降级链只剩一层底板:
```
text_mode 聊天批(地板,无浏览器/无 curl 时)
  → live web-review(curl /wait 长轮询,跨引擎实时;feedback.json 仍写盘作 file 兜底)
```
注:`AskUserQuestion` 仍是 CC 专属,但它只在 revise seam 的可选追问里(§3.3),**不在核心 await 路径上**,Codex 上降级 text_mode 即可。核心 loop 全可移植。

### 3.3 单渠道纪律(AUQ 的位置)
`AskUserQuestion`(AUQ)是内置工具,排除不掉。但与 web 不会打架——**时间天然隔离**:web round 进行时 agent 正前台阻塞在 `curl /wait` 上,物理上发不出 AUQ;AUQ 只能出现在 `/wait` 返回后的 **revise seam**(改之前的跟进追问,如"3 条都改还是只改 #1#3?")。纪律一条:**同一时刻只允许一个活跃渠道**(浏览器 round ⟂ 终端 revise)。Codex 无 AUQ → 该追问降级 text_mode(铁律 #2 不破)。

## 4. 架构(组件:4 复用[其一微调] + 1 新原则)

| 单元 | 来源 | 职责 | 改动 |
|------|------|------|------|
| Renderer (`build.py`) | 复用+微调 | md → 可批注 HTML | **模板注 ~6 行 `/rev` 刷新 poller**;渲染逻辑零改 |
| 批注层 (`annotate.js/css`) | 复用 | 划词→评论→高亮→面板→`POST /feedback`(含 verdict) | 零改 |
| Collector (`server.py`) | 复用+扩展 | 托管页 + `POST /feedback` + 静态 serve `/rev` | **换 `ThreadingHTTPServer` + 加 `/wait` 长轮询端点**;`/feedback` 语义不变(加 `event.set()`) |
| **Loop 编排** | **新(playbook 纪律)** | present→`curl /wait`(阻塞)→apply→bump `rev`→rebuild→循环 | playbook 新增 |

铁律 #4(约束做什么不规定怎么执行):await 写成**原则**——"agent 前台阻塞 `curl /wait` 直到用户提交;超时则 re-arm",附最小示例,不写死脆弱一行流。`server.py` 的 `/wait` 是**工具资产**(命令/端点即交付物,保留具体实现,符合铁律 #4 对参考卡/资产的例外)。

## 5. 数据流 / 循环

```
build.py 渲染→outdir │ server.py(ThreadingHTTPServer)起一次(常驻, 绑 127.0.0.1) │ 开浏览器
└─ round loop:
   agent 前台: curl -s -m545 /wait   ← 阻塞,直到↓
       〔用户读 + 划词 + 选 verdict + 提交〕  POST /feedback → event.set() → /wait 释放
   curl 返回 {doc,verdict,count,annotations:[{id,section,quote,comment}]}  (204=超时→re-arm)
   ├ verdict=approve 且无阻断批注 → 跳出 → 停 server → 回判对应 stage 的 gate
   └ verdict=changes → 按 section+quote 定位逐条改源 md
                       →(可选)revise seam 用 AUQ 追问取舍
                       → date +%s > rev (bump) → rebuild → 页面自动 reload → 回 loop
```

### 5.1 自动刷新(⑤)
build.py 模板注入 poller:每 ~2s `fetch('/rev')`,值变则 `location.reload()`。loop 每次 rebuild 前 `date +%s > outdir/rev`。`server.py` 把 `rev` 当静态文件返回(`/wait` 之外的 GET 走 `super().do_GET()`)。无 `/rev` 时 poller 静默失败、退化手动刷新(可降级)。

### 5.2 server.py 扩展 + agent 侧(参考实现)
server.py 关键扩展(线程 + 长轮询):
```python
import threading
slot = {"data": None}; ev = threading.Event()
class Handler(SimpleHTTPRequestHandler):
    def do_GET(self):
        if self.path.rstrip('/') == '/wait':
            if ev.wait(timeout=540):
                data = slot["data"]; ev.clear(); slot["data"] = None
                self._json(200, data)            # 释放挂起请求,回批注
            else:
                self.send_response(204); self.end_headers()   # 超时→agent re-arm
        else:
            super().do_GET()                     # 页面 / /rev 静态
    def do_POST(self):                           # /feedback,语义不变 + 唤醒
        body = self.rfile.read(int(self.headers.get('Content-Length', 0)))
        open('feedback.json','wb').write(body)   # 仍写盘=durable 兜底
        slot["data"] = body; ev.set()
        self._json(200, b'{"ok":true}')
# 必须多线程:挂起的 /wait 否则堵死 POST → 死锁
ThreadingHTTPServer(('127.0.0.1', PORT), Handler).serve_forever()
```
agent 侧(前台阻塞一次):
```bash
out=$(curl -s -m 545 -w '\n%{http_code}' http://127.0.0.1:$PORT/wait)
code=${out##*$'\n'}; body=${out%$'\n'*}
# code=200 → body 是 {verdict,annotations[]};  204/000 → 再 curl 一次(re-arm)
```
**竞态**:用户在 agent arm `/wait` 前就提交 → `ev` 已 set,下个 `/wait` 立即返回,不丢提交。
**file 兜底**:无 curl/浏览器的引擎 → 退回读 `feedback.json`(仍写盘)或 text_mode。

## 6. 错误处理

| 情况 | 处理 |
|------|------|
| quote 在源 md 匹配不到 | 回报该条请用户澄清,**不臆改**(沿用 playbook §3.6) |
| `feedback.json` 损坏 / 非法 JSON | 报错,请用户重提交 |
| 端口占用 | 起 server 前先清占用端口 |
| `/wait` 超时(540s 无提交,回 204) | agent 直接 re-arm(再 curl);连续多次空转可问用户"继续等 / 停" |
| 无浏览器 / 无 curl | 降级:告知 URL 让用户开;`curl` 不可用→读 `feedback.json` 兜底;再不行回 text_mode |
| 多轮 round 串扰 | `ev.clear()` 后重新 arm;`/feedback` 覆盖写,单轮一份 |
| `/wait` 挂起堵死其他请求 | **必须 `ThreadingHTTPServer`**(每请求独立线程),否则死锁——P2 核心约束 |

## 7. 落地(改哪些文件)

| 文件 | 改动 |
|------|------|
| `references/web-review/server.py` | **换 `ThreadingHTTPServer` + 加 `/wait` 长轮询端点**(`threading.Event`/slot);`/feedback` 加 `event.set()`,语义不变 |
| `references/web-review/playbook.md` | 新增「§6 Live mode」:`curl /wait` await 原则 + loop 纪律 + 单渠道纪律 + file/text_mode 兜底 |
| `references/web-review/build.py` | 模板注 ~6 行 `/rev` poller 自动刷新 |
| `skills/sdlc-spec/SKILL.md` · `skills/sdlc-plan/SKILL.md` | 复核 gate 处加一行:"可选 live 模式(curl /wait 实时回流,跨引擎),见 web-review playbook §6" |
| `CHANGELOG.md` | 记本次增强 |
| `.claude-plugin/{plugin,marketplace}.json` | 升 version(语义化,minor) |

## 8. sdlc-pilot 维护契约(实现时必守)

- 本质 = 对工具自身的 **append-only 小改** → 走 `/sdlc evolve` 那条线最正(lint + additive 守卫 + 人工过目)。
- 提交前跑 `bash scripts/validate-skills`,不过不提交。
- 更新 `CHANGELOG.md` + 升 version。

## 9. 测试

- **长轮询单测(可重复)**:起 server → 后台开一个 `curl /wait` → 另一进程 `curl -X POST /feedback -d '{...}'` → 断言 `/wait` **立即返回**且 body == 提交内容;再测无提交时 545s 内回 204(可缩短 timeout 跑)。验证 threading 不死锁。
- 主:**dogfood**——样例 md 跑一轮:render→serve→开页;模拟 `POST /feedback`;验证 ① `curl /wait` 即时返回正确 JSON、② 批注按 section+quote 正确 apply、③ bump `rev` 后页面自动 reload、④ Codex 引擎下同样能 `curl /wait` 拿到(可移植性验证)。
- 结构:`scripts/validate-skills`(frontmatter / 引用一致)。
- 编排类 playbook 无法单测,以 dogfood 为准(同 sdlc 既有测法)。

## 10. 开放问题

无阻断项。`rev` 自动刷新若在某些浏览器/file:// 下行为异常,降级手动刷新(已含在 5.1)。
