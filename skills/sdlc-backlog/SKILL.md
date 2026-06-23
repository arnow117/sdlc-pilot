---
name: sdlc-backlog
description: >
  SDLC 主线的 pre-spec 阶段:把"一堆散点需求 / 一个待重写的老系统"测绘成一棵可路由的
  需求树(产出 <target-repo>/.sdlc/requirements/ 递归 domain→subdomain→leaf)。管的是 spec
  之前的【需求集合】:Seed(老系统→骨架)、Generate(分析代码→自动 gen 带叶的 capability/user-story 树,多 agent)、Ingest(散点需求归类成叶)、Coverage(迁移 burndown)、
  Ready-queue(派生解依赖的就绪叶 → 喂给未来的 sdlc-loop)、Lint(断依赖/重复/孤儿/缺字段/非法 status)、
  set-status(机械改叶 status,叶生命周期同步原语,供 post-checkout 钩子/driver reconcile 调)、
  视图导出(Tree=整树嵌套 JSON 给 agent / Board=折叠树 HTML 看板给人看,复用 web-review annotate 补 review gate)、
  Move(叶迁域:mv 文件+改 id/domain_path+改写依赖)、
  Retire(特性 done 退场:归档工件/回流教训到 EVOLUTION/标源叶 shipped 并把同条教训写进该叶 `## sdlc 记录`/清栈——backlog 因此成为特性生命周期的两端书挡)。
  触发于:用户说 "建需求树"、"管理需求 backlog"、"散点需求记一下/归档"、"Ingest 这条需求"、
  "老系统重写要把功能点都列出来"、"迁移覆盖到哪了"、"选下一条需求做"、"sdlc-backlog";
  driver 在检测到 <target-repo>/.sdlc/requirements/ 存在且无进行中特性时也路由到此。
  本 skill 只管需求集合:不收敛单条需求(那是 sdlc-spec)、不拆任务(sdlc-plan)、不写实现、
  不调度 loop(那是子系统 B / 未来)。它产出 ready-queue 契约,供调度器消费。
---

# sdlc-backlog — pre-spec 阶段:需求树 / backlog

把"业务侧散点式冒出来的需求"和"一个待重写老系统的全部功能点",收进一棵**递归需求树**,
让需求**不丢、可归类、覆盖度可观测**,并派生出一个**就绪队列(ready-queue)**供调度器(子系统 B)消费。

> **它在生命周期里的位置**:`backlog` 是**项目级 stage**(与 `onboard` 同类——产项目级长寿 artifact,
> 不属单特性生命周期)。从需求树选中一片叶后,**另起**一条单特性 STATE,stage 从 `spec` 起跑
> spec→plan→build→validate→review→ship。backlog 与单特性 STATE **解耦**(互不覆盖)。
>
> **边界**:本 skill 管"需求集合"。收敛单条需求 = `sdlc-spec`;拆任务 = `sdlc-plan`;调度循环 = 子系统 B。
> 知识与状态全在纯文件,引擎 = Claude + Read/Edit/Bash/Grep。
>
> distilled-from: `session:loop-engineering-article(Addy Osmani)` · `kb-manage`(递归 domain-subdomain + Ingest) · `tb-loop-driver`(导演/编排模式) · `session:sdlc-backlog-build-2026-06-15` · `session:sdlc-feature-retirement-2026-06-16`(Retire op / 特性退场闭环) · `session:sdlc-backlog-board-2026-06-16`(Tree/Board/Move op + 聊天看板 + Live 对话模式) · `session:sdlc-evolution-leaf-attach-2026-06-16`(Retire 标 shipped 时把 evolution entry 也写进源叶 `## sdlc 记录`) · `session:sdlc-tree-generator-2026-06-16`(Generate op:分析代码→capability/user-story 树 + 4 交叉字段 + write-tree + 多 agent 两阶段) · `session:sdlc-leaf-lifecycle-board-2026-06-23`(set-status op + 叶生命周期状态同步 C 混合写回[post-checkout 钩子+driver reconcile]+ 看板重构 4 痛点 + lint bad-status)

---

## 0. 可移植前置(每次入口先做)

本 skill 必须在 Claude 和 Codex 下都能跑。两条降级范式:

### 0.1 交互降级 — text_mode(默认开)
凡需向用户提问(确认 Seed 骨架草案、Ingest 归类二义、选主分类),**默认用纯文本编号列表**,
不硬依赖 AskUserQuestion:

```
这条需求像是跨了两个 subdomain,你定个主分类:
  1) order/checkout — 它主要影响结算页
  2) promo/coupon  — 它主要属于优惠券域
回复编号即可(我会把另一个写进 cross_link)。
```
有 AskUserQuestion 时可用,但回退路径必须是上面这种编号文本。

### 0.2 并行降级 — Task-or-sequential
批量 Ingest(一次喂进很多散点需求)时:有 Task/并行能力 → 可一需求一 agent 起草归类,各写各自叶文件;
无并行能力(Codex 等)→ 串行逐条 Ingest。**任何时候不得让两个写手同写同一叶文件 / 同一 `_index.md`**(单写者)。

---

## 1. 数据模型(事实源 = 叶 frontmatter)

### 1.1 树存储(文件系统递归镜像)

数据落在**目标项目**(非本 skill 仓):

```
<target-repo>/.sdlc/requirements/
├── _index.md                 # 派生产物:覆盖 burndown + ready-queue 快照(由 Coverage/Ready-queue 重生成,可随时重建)
├── <domain>/
│   ├── _domain.md            # domain 元信息(old-system 模块映射 + new_domain 对应)
│   └── <subdomain>/
│       ├── _subdomain.md     # subdomain 元信息
│       └── <leaf-id>.md      # 一条具体需求(叶)
```

- **递归**:subdomain 下可再嵌 subdomain(`domain→subdomain→…→leaf`),与 kb-manage 的 domain/subdomain/entity 同构。
- **每叶独立文件** → 单写者友好、git-diffable、并行 Ingest 不互锁。
- **`_index.md` 是派生产物**,不是事实源;事实源永远是各叶文件的 frontmatter。`_index.md` 可由 `scripts/backlog.py` 随时重建。

### 1.2 叶 schema(`<leaf-id>.md` frontmatter,10 必填字段)

```markdown
---
id: <domain>.<subdomain>.<slug>          # 全局唯一,与文件路径一致
title: <一句话需求>
domain_path: <domain>/<subdomain>        # 主分类(唯一)
cross_link: []                           # 次分类:跨 subdomain 时挂多父(解二义)
old_system_ref: <老系统模块/页面/接口/故事编号>   # 双视图之一(迁移对齐)
new_domain_path: <新系统归属,可与 domain_path 不同>  # 双视图之二(rewrite≠1:1)
status: captured                         # captured → spec'd → planned → built → validated → shipped
priority: P2                             # P0 | P1 | P2 | P3
depends_on: []                           # 其它 leaf id,构成依赖 DAG
risk_level: medium                       # low | medium | high(供子系统 B 的成本/gate 分诊)
updated: <date>
# —— 以下 4 个为【可选交叉视图字段】(生成器 #6 填;非必填,不进 REQUIRED_FIELDS;存量叶不填仍 lint clean) ——
actor: <参与者/角色>                      # 可选:该需求服务哪个角色(供应商/运营/采购/集成方…)
failure_class: <funds|consistency|compliance|experience>  # 可选:失败代价类(资金正确性/数据一致性/合规信任/体验);lint 校验枚举
contract_refs: []                        # 可选:list,关联的契约路径(OpenAPI/包间契约);lint 校验须为 list
data_owner: <数据真相源>                  # 可选:该需求读/写哪份数据的真相源
---

## 需求描述
（散点需求原文 + 澄清后的意图）

## 验收线索
（怎么算这片叶 done 的初步线索;正式验收在 sdlc-spec 阶段细化）

## 老系统行为参照
（old_system_ref 指向的实际行为,供 rewrite 对齐）
```

**双视图(解 R1:rewrite ≠ 1:1 移植)**:`old_system_ref`(老系统怎么做)与 `new_domain_path`(新系统归到哪)
同时记,覆盖图既能按老系统盘点"迁完没",又能按新架构组织。

**多父(解 R2:散点需求跨 subdomain 二义)**:`domain_path` 唯一(主分类),其余归属写 `cross_link[]`;
Lint 会查"同 old_system_ref 出现在多叶"的重复。

### 1.3 ready-queue 契约(A 产出 / 调度器消费)—— 对外稳定面

```
Ready-queue(由 `scripts/backlog.py readyqueue` 派生,写入 _index.md ready 段):
[
  { leaf_id, title, priority, deps_resolved: true, old_system_ref, risk_level, status },
  ...
]   # ready ⟺ 自身 status != shipped(已完成的叶不入队) 且 depends_on 全部 shipped(或为空)
    # 按 priority 升序键(P0<P1<P2<P3)、同级按 id 排序
```

子系统 B(sdlc-loop)只依赖这个结构,不依赖树的内部存储细节 → A/B 解耦,可独立演进。
**终态 `shipped` 回写**由本 skill 的 **Retire 操作**(§6,特性 done 时)负责——填上原先悬空的回写点,
ready-queue 据此自动解锁下游叶。中间态(captured→spec'd→planned→built→validated)的逐阶段回写
与调度循环仍属未来子系统 B(本仓本特性 spec §8 已 Deferred)。

---

## 2. 操作: Seed(老系统 → 骨架)

**何时**:启动一个老系统 rewrite,要先把"有哪些域/模块"立成骨架,再往里填散点需求。

**输入**:老系统结构(用户描述,或 agent 读老系统代码/文档/菜单整理)。

**行为**(只建骨架,不造叶):
1. 与用户对齐 domain 划分(text_mode 给草案让其增删改)。
2. 在 `<root>/<domain>/<subdomain>/` 建目录;写 `_domain.md` / `_subdomain.md`,各记:
   - `old_system_module`:对应老系统的哪个模块/菜单/服务;
   - `new_domain`:新系统里预期归到哪(可与目录名不同,落 R1 双视图骨架);
   - 一句范围说明。
3. **不自动造叶**——空 subdomain 即"待覆盖清单"(后续靠 Ingest 填;Coverage 会把空 subdomain 高亮成"未迁功能")。

**纪律**:Seed 只立结构、不臆造需求。拿不准某模块归哪个 domain → text_mode 问,不硬塞。

**产出**:`<root>/<domain>/<subdomain>/` 骨架 + `_domain.md`/`_subdomain.md`。

### 2.7 操作: Generate(从代码逆向出**带叶**的树 · #6)

Seed 只建空骨架靠人 Ingest。Generate 把它升级为**分析已有 codebase → 自动产出带叶的需求树**(已有项目 → 树 → #4 看板 → 选叶起特性的闭环)。这是**判断性 agent-playbook**(像 onboard 读码,不是确定性脚本;机械落盘交 `write-tree` 脚本)。

> **何时**:对一个已有项目要"从代码逆向出 backlog 全景"。**产物用途 = PM↔业务对齐** → 主轴必须业务可读。

**主轴与叶(轴决策,见 spec §4)**:
- **主轴 `domain_path` = 功能/用户故事**:domain = 功能域/epic(入驻/商品/订单/结算/集成…),叶 = **业务可读的用户故事**「作为<角色>,我要<能力>,以便<价值>」。
- **禁工程术语命名叶**(不叫"实现 OrderService.settle()",叫"运营能对已履约订单发起结算");工程细节(状态跃迁/契约/类)只进 `## 老系统行为参照` 或交叉字段,**不进标题**。
- **叶粒度自适应**:一条可独立交付的用户故事/功能;**内部用状态跃迁辅助定粒度**(使 `depends_on` 天然无环:创建先于履约),但不主导标题;**每 domain 叶数软上限(≤~12)** 防碎片化,超则合并/上提 subdomain。
- **4 交叉字段(能推断则填)**:`actor`(角色)/`failure_class`(funds|consistency|compliance|experience)/`contract_refs`(契约路径 list)/`data_owner`(数据真相源)。`old_system_ref`/`new_domain_path` 从模块/契约路径填双视图。
- **★`status` 推断 = 代码完整度的 draft 猜测,不是生命周期真值(dogfood 教训)**:从代码状态推断——**空实现/TODO/占位骨架 → `captured`；实现了但有缺口/无调用方 → `built`；完整实现 + 有测试覆盖 → `validated`**。
  - **关键语义修正**:`status` 状态机(captured→spec'd→planned→built→validated→shipped)记的是**该需求走 SDLC 到哪了**;而生成器只能看见**代码完整度**——二者不同。"代码写完+测试覆盖"映射到 **`validated` 封顶,不要给 `shipped`**(`shipped` = 走完整 SDLC/有发布证据,代码看不出来)。
  - **必须当 draft**:推断的 status **很可能与项目真实生命周期 status 不一致**(如代码完整但该需求其实还没正式上线)→ 在预览/落盘时**显式标记为推断值**,**靠人审闸(§下 步骤4)逐域校正**,不可当权威。`old_system_ref` 记下据以推断的代码位置,供人复核。

**输入(复用,不重造分析轮子)**:优先读 `<target-repo>/.sdlc/PROFILE.md` 的 surface-map(onboard 产的"模块→面"骨架,**无 PROFILE 则先跑 sdlc-onboard**);再深读 `contracts/`(OpenAPI 端点)、模块子目录、`db/schema`(实体)、`CLAUDE.md`/`docs`(业务意图)。

**运行 = 多 agent 两阶段(分析慢,必须并行;复用 Task-or-sequential + 单写者,同 sdlc-review)**:
1. **阶段1(orchestrator 单趟,便宜)**:从 surface-map + 业务线索/契约归纳【功能域列表】(domain 骨架)。**域列表可先给人审一眼**再 fan-out(防分析方向跑偏后白跑 N 个 agent)。
2. **阶段2(fan-out,并行)**:**一功能域一 agent**,各自深读该域相关代码/契约 → 产该域用户故事叶(含 status/depends_on/4 交叉字段),**各写各的草稿** `<tmp>/gen/<domain>.json`,**互相隔离**(不把一个域的产出喂给另一个 → 避免锚定)。无 Task → 串行 inline 逐域跑同一规程。
3. **合并(orchestrator,单写者)**:跨域去重 + 跨域 `cross_link`(一个故事跨 2 域)+ 跨域 `depends_on` 保无环 + 每域叶数上限 → 汇成一份 merged tree JSON。
   - **★规范化门(write-tree 前必做,dogfood 教训)**:fan-out agent 的原始输出**常不严格合 schema**——逐叶规范化:`priority` 必 ∈ {P0,P1,P2,P3}(误填 high/medium/low → 映射 P1/P2/P3);`domain_path` 必**斜杠分隔且 ≥2 级**(误用点号 `a.b` → 改 `a/b`;单级 → 补子域如 `<x>/general`);`new_domain_path` 必是**域路径非代码路径**(误填 `apps/...` → 回填 = `domain_path`);`failure_class` 若存在必 ∈ {funds,consistency,compliance,experience};`contract_refs` 必 list。不合规就地修或回退该叶。**否则 `write-tree` 落盘后 `lint` 必挂**。
4. **人审预览(硬闸)**:把 merged tree 渲染成 #4 `board` 看板(或网页审)让人**剪枝/改/确认** —— 生成质量不稳时,人在落盘前把关。
5. **落盘**:`python3 <bk> write-tree --root <root> --from <merged.json>`(机械写叶,已存在跳过)→ `python3 <bk> lint --root <root>` 必须 clean。

**降级**:无 PROFILE 且用户不想 onboard → 仅从顶层结构 + contracts 粗粒度生成、标 PARTIAL、提示 onboard 后细化;推断不出某交叉字段 → 留空(可选)。

**纪律**:Generate 是 agent 判断 + 脚本落盘的混合;**单写者**(草稿各写各的,只 orchestrator 合并后经 `write-tree` 落盘);叶必须业务可读 + 可写验收线索;不臆造代码里没有的能力(基于真实 surface)。

**产出**:`<root>/` 下带叶的 capability/user-story 树(lint clean),可直接喂 #4 看板 + ready-queue。

---

## 3. 操作: Ingest(散点需求 → 叶)

**何时**:业务侧冒出一条需求 / 从 session 线索 / 从老系统某行为,要把它**归一条进树**。

**输入**:一条散点需求原文(+ 可选老系统行为参照)。

**行为**:
1. **归类**到 `domain→subdomain`:
   - 命中已有 subdomain → 在其下建叶;
   - 未命中 → text_mode 提示"新建 subdomain / 还是挂到最近的 cross_link";
   - **跨多个 subdomain(二义)** → text_mode 让用户选**主分类**(写 `domain_path`),其余写 `cross_link[]`。
2. **建叶文件** `<domain>/<subdomain>/<leaf-id>.md`,`id` 与路径一致;填全 §1.2 的 10 字段:
   - `status` 默认 `captured`;`priority`/`risk_level` 询问或默认 `P2`/`medium`;`depends_on` 留空待补;
   - `old_system_ref` 尽量填(rewrite 场景这是迁移锚点);`updated` 用 caller 传入日期(不自造时钟)。
3. 需求原文写进叶的 `## 需求描述`,老系统行为写进 `## 老系统行为参照`。
4. 批量 Ingest 见 §0.2(可并行,各写各叶)。

**纪律**:一条需求归一片叶(主分类唯一);拿不准就问,别一条需求拆成多叶造成重复(Lint 会抓重复)。

**产出**:一个/多个带全字段 frontmatter 的合法叶文件。

---

## 4. 派生操作(Ready-queue / Coverage / Lint)

这三个是**机械、确定性**的派生,由 sdlc-pilot 的 `scripts/backlog.py`(纯标准库)承载——避免每次用易错的 ad-hoc grep。
**事实源永远是叶 frontmatter**,脚本只读派生,不改树。`<bk>` = sdlc-pilot 仓的 `scripts/backlog.py` 路径;`<root>` = `<target-repo>/.sdlc/requirements`。

### 4.1 Ready-queue —— A/B 契约的产出
```
python3 <bk> readyqueue --root <root>
```
输出 §1.3 的 ready-queue JSON(就绪叶,priority 排序)。用途:子系统 B(调度器)dequeue 下一片来跑;
也可把结果写进 `<root>/_index.md` 的 ready 段作快照(快照非权威,随时可重生成)。

### 4.2 Coverage —— 迁移 burndown
```
python3 <bk> coverage --root <root>
```
按顶层 domain 输出 `{total, by_status:{...}}`。用途:看 rewrite 迁到哪了——某 domain 的 `shipped` 计数 vs 总数;
空 subdomain(无叶)= 老系统里还没被 Ingest 进来的功能,即"未覆盖"线索。

### 4.3 Lint —— 树的 correctness
```
python3 <bk> lint --root <root>
```
报问题并以非 0 退出码标记:① **dangling-dep**(depends_on 指向不存在 id)② **dup-old_system_ref**
(同 old_system_ref 出现在多叶,提示一条需求被重复 Ingest)③ **missing-field**(10 必填 frontmatter 缺任一)
④ **orphan**(叶不在 `<domain>/<subdomain>/` 形态下)⑤ **bad-status**(status 取值不在 STATUS_ORDER 枚举)
⑥ **bad-failure-class / bad-contract-refs**(4 可选交叉字段取值非法)。lint 只**报**不**修**,问题清单 text_mode 给用户决策。
这就是需求树的 correctness 门(对应 validate 阶段)。

### 4.3b set-status —— 机械改叶 status(生命周期同步原语)
```
python3 <bk> set-status --root <root> --leaf <id> --to <status>
```
把指定叶 frontmatter 的 `status` 机械改为目标值(须 ∈ STATUS_ORDER:captured→spec'd→planned→built→validated→shipped)。
**allow-any 迁移**:只校验目标值合法,不查迁移合法性(可前进可回退);叶不存在 exit 2、非法值 exit 1、成功 exit 0。
这是**叶生命周期状态同步**(C 混合写回)的共享机械写原语,主要由两处自动调用,人手亦可用:
- **post-checkout git 钩子**(硬层):切分支时把在飞特性源叶 status flush 落盘(过渡态不丢)。
- **driver §1.1b reconcile**(软层):driver 入口对账,叶 status 落后 STATE.stage 映射值则补齐(只前进)。
稳态(captured/shipped)落盘持久,过渡态(spec'd→validated)平时由看板读 STATE 惰性叠加显示(不写文件),离开特性时由钩子/reconcile flush。

### 4.4 Tree —— 整树嵌套 JSON(agent 视角)
```
python3 <bk> tree --root <root>
```
把整棵树导成 `domain→subdomain→leaf` 嵌套 JSON(每叶含 9 对外字段)+ `summary`(total / by_status / ready_count)到 stdout。与 readyqueue(就绪切片)、coverage(状态计数)互补:tree 给的是**全貌结构**,供 agent/调度器一次拿到整棵树。**只读**,事实源仍是叶 frontmatter。内部嵌套逻辑 `build_tree(leaves)` 与 board 共用(DRY)。

### 4.5 Board —— 折叠树 HTML 看板 + 聊天 chatbot(人看 + 对话编辑)+ review gate
```
python3 <bk> board --root <root> [--out <path>]    # 默认 <root>/_board.html
```
渲染**自包含 HTML 看板**(纯标准库拼装,内联 CSS+JS,无模板引擎/网络字体,离线可开),视觉遵仓根 `DESIGN.md`(暖奶油/鼠尾草绿):
- **左:三级折叠树** `domain→subdomain→leaf`(原生 `<details>`,叶卡带 status 徽章/priority/risk/依赖 + 每 domain coverage 进度条),点叶=选中。
- **右:聊天面板(chatbot)** —— 选中叶后顶部显示该叶**完整详情**(字段 + 需求描述/验收/老系统正文,经 `leaf-data` JSON 嵌入),下方 per-leaf 对话气泡 + 输入框。**不依赖 annotate.\***(聊天自建)。
- **只读渲染**:看板本身不写树;改树由 agent 经 `Edit` / `move` 落地(守单写者)。

**起服**:把 board 输出复制为 `index.html`,与 `sdlc/references/web-review/server.py` **同目录**(server.py 从自身目录提供静态文件 + `/feedback`/`/wait`/`/rev`),写个 `rev` 文件,`python3 server.py <port>` 绑 127.0.0.1 开页。**只需 server.py**(不再需要 annotate.css/js)。

#### ★ Live 对话模式(agent 操作规程 + 用户须知)
看板默认是**留言板**:用户发的消息进 `feedback.json` + 追加 `feedback-history.jsonl`,**agent 不在场就不会回**。要做到**实时对话应答**,agent 主动切入 Live 循环(present → await → revise,蒸馏自 web-review playbook §6):

1. **await**:agent **前台阻塞** `curl "http://127.0.0.1:<port>/wait?t=240"`,挂起等用户提交;返回 `{id,leaf,message}`,或超时回 204 则 re-arm。
2. **act**:按消息意图处理——**追问**=读该叶答疑;**完善**=`Edit` 叶 `.md` 字段/正文;**迁域**=`backlog.py move`;**新增需求**=Ingest 新叶。**改了树就重渲染 board + bump `rev` 文件**(页面轮询 `/rev`,值变即 reload)。
3. **reply**:把回复写进 serve 目录的 `replies.json`(**累积合并**,键=消息 `id`;页面轮询 `/replies.json` 追加 agent 气泡)。线程持久化靠 `feedback-history.jsonl`+`replies.json`,刷新不丢。
4. **re-arm**:再 `curl /wait` 回到 1。

- **单渠道纪律**:agent 阻塞 `/wait` 期间发不出别的交互(会话被占);要结构化追问只在 `/wait` 返回后的 seam 做。一次只一个活跃渠道(浏览器轮 ⟂ 终端 revise)。
- **用户须知(要在对用户的话术里说清)**:要实时对话,需让 agent **切到 live 监听**(它会**占住当前会话**,期间只做这件事);不切则消息排队,等 agent 下次在场批量处理。**真·无人值守自动应答 = 独立 daemon(本特性 Deferred,见 spec §8)**,不在看板核心内。

> **这等于给 backlog 补一道人看 + 对话可编辑的 review gate**:树渲染出来给人审,选叶看详情,聊天里直接让 agent 改/迁/补。

---

## 5. 操作: Move(叶迁域)

**何时**:一片叶归错了域 / 评审中决定把它移到另一个 `domain/subdomain`(常由 Board 上的请求触发)。

**输入**:`--leaf <id>` 要迁的叶、`--to <domain>/<subdomain>` 目标域。

```
python3 <bk> move --root <root> --leaf <leaf-id> --to <domain>/<subdomain>
```

**行为**(确定性机械写,与 retire 同类):① mv 叶文件到目标目录;② 改 frontmatter `id`(= `<目标域>.<slug>`)与 `domain_path`;③ **改写全树中指向旧 id 的 `depends_on` 引用**(防断依赖)。**幂等守卫**:目标已存在同 id → 拒绝、非 0 退出、不动文件(仿 retire)。源叶不存在 → 非 0。

**纪律**:move 是 `backlog.py` 第 2 个**写树** op(retire 之后;派生 op 仍只读)。它是该时刻树的唯一写者(单写者)。迁域只动归属,不改需求语义;跨域二义(既属 A 又属 B)用 `cross_link` 而非 move。

---

## 6. 操作: Retire(特性退场 / close-out)

**何时**:一个单特性走到 `stage=done`。由 **driver** 在 `/sdlc` 入口检测到 `STATE.stage==done` 时路由进来(见 sdlc driver §2/§4),给完成的特性收尾。这是 backlog 在生命周期**末端**的职责——与"选 ready 叶起特性"(§7 出口的开端)首尾呼应。

**输入**:`<target-repo>/.sdlc/`(含本特性的 spec/plan/validate/review/STATE)、`STATE.source-leaf`(若特性源自需求树)、`STATE.Decisions log`。

**四步**(确定性部分 = `scripts/backlog.py retire`;判断性部分 = 模型蒸馏):

| 步 | 动作 | 谁做 | 普适 |
|---|---|---|---|
| ① 归档 | `.sdlc/{spec.md,plan.md,validate,review,STATE.md}` → `.sdlc/archive/<date>-<slug>/` | 脚本 | 全部特性 |
| ② 回流 | 从 `STATE.Decisions log` 蒸馏**耐久**决策/教训/新风险成一行,append `.sdlc/EVOLUTION.md` | **模型蒸馏** + 脚本追加 | 全部特性 |
| ③ 标 shipped + 写叶 sdlc 记录 | 源叶 `status=shipped` → ready-queue 自动解锁下游叶;**若同时传了 `--evolution-entry`,同条也 append 进该源叶 `.md` 的 `## sdlc 记录` 段**(使需求树成带 sdlc 记录的活档案——每叶随身记着它 ship 时的耐久教训) | 脚本(`--leaf`+`--req-root`[+`--evolution-entry`]) | **仅** 源自需求树的特性 |
| ④ 清栈 | STATE.md 随①移走 → 顶层留空,交还给下个特性 | 脚本(随①完成) | 全部特性 |

```
python3 <bk> retire --sdlc <target>/.sdlc --slug <feat> --date <YYYY-MM-DD> \
  [--leaf <leaf-id> --req-root <target>/.sdlc/requirements] \
  [--evolution-entry "<蒸馏出的一行>"]
```

**确定性 vs 判断性**:文件移动 / 标 shipped / 追加 = 脚本(确定性,命令即交付)。**"哪些决策值得回流"= 模型判断**——判据:**跨特性仍成立**的架构/契约决策、踩过的坑、新发现的风险才回流;一次性实现细节**不**回流。模型据此从 Decisions log 蒸馏出一行,经 `--evolution-entry` 传入(或直接编辑目标文件)。

**回流目标(②)**:唯一正屋 = `<sdlc>/EVOLUTION.md`(脚本统一 append,缺则建 `# Evolution log` 头)。`PROFILE.md` **不承载流水**,仅留一行指针(见 PROFILE 模板)——因 Evolution log 是无界流水、PROFILE 六节是有界快照,本性不同故分文件。这是长寿、可跨会话/sub-agent 复用的"演进记忆",区别于 archive(本地工件留存)。

**叶挂载(③ 的附带)**:当 `--leaf` 命中且有 `--evolution-entry` 时,脚本把**同一条** entry 也 append 进该源叶的 `## sdlc 记录` 段(段缺则建)。EVOLUTION.md 是**全局**流水,叶 `## sdlc 记录` 是**该需求**的本地记录——二者并行、互不替代。无叶或无 entry → 不挂(降级)。`_mark_leaf_shipped` 命中返回叶路径供此挂载;retire 仍是该时刻唯一写者。

**优雅降级**:无 `requirements/` 树、或特性非源自叶(无 `source-leaf`)→ 跳过③,①②④照做(脚本 `--leaf`/`--req-root` 缺省即跳过)。

**幂等安全**:`archive/<date>-<slug>/` 已存在 → 脚本拒绝覆盖、非 0 退出、不动任何文件(防重复退场误删)。

**单写者**:Retire 是该时刻 `STATE.md` 的唯一写者(driver 路由进来后 backlog 独占),归档→清栈原子完成。

> 注:retire 是 `backlog.py` 唯一**写树**的操作(派生 op 只读);它只标终态 `shipped`,不重算 `_index.md`(ready-queue 按需派生,下次 readyqueue/coverage 自动反映)。

---

## 7. 出口 / 交接

- backlog 操作不推进单特性 stage;它维护项目级需求树 + 特性退场。
- 选中一片 ready 叶进入开发 → 由 driver 另起单特性 STATE(stage=spec),把该叶的 `id` / 需求描述 / `old_system_ref` 作为 sdlc-spec 的输入(开端)。
- 特性 done → driver 路由 Retire 收尾(末端):归档 + 回流 + 标源叶 shipped + 清栈。
- 需求树本身的"correctness" = `scripts/backlog.py lint` 干净(无断依赖/重复/孤儿/缺字段)。

## 8. 不做什么(边界)

- ❌ 不收敛单条需求成 spec(那是 sdlc-spec)。
- ❌ 不拆任务、不写测试、不写实现(plan/build)。
- ❌ 不调度循环、不自动跑 pipeline(子系统 B / 未来)。
- ❌ Seed 不臆造需求;Ingest 不把一条需求拆成多叶。
- ❌ 不把 `_index.md` 当事实源(它是派生产物,事实源 = 叶 frontmatter)。
