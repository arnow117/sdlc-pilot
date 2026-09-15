---
title: 源码协作纪律（分支 / 命名 / 提交 / worktree / 并行收敛）
scope: methodology                # 通用、跨语言、跨目标——不含项目特定值
applies-to: sdlc(driver §1.1, 跨阶段) + sdlc-build §0.2   # driver 在 entry 加载、贯穿 plan→build→review;build 用于提交/波内执行
distilled-from: [session:collaboration-discipline-2026-06-23, session:portal-auth-multiagent-loop-2026-06-24]
updated: 2026-06-24
---

# 源码协作纪律 · collaboration-discipline

> 通用方法论卡:回答"多人/多 agent 共享一个代码库怎么不打架"。技术栈无关；派工、层级、验收、检查点和
> 纠偏唯一遵循 [`stage-agent-protocol.md`](stage-agent-protocol.md)。
> 第一性原理:① 集成成本随分叉时长增长;② 并行的代价是把集成推迟;③ 隔离的 agent 之间**没有共享上下文** → 协调必须**前置**。本卡只给约束与原则,具体命令用稳定 git 原语示意。

---

## 1. 分支模型(按意图分两类,不一刀切)

"短命"只在**目标是收敛(要合回主干)**时成立。先判:这条分支要不要并回主干。

- **A 收敛型(feature/fix/hotfix)= 短命默认**
  - 从已接受的集成基线切短命分支，保持分叉时间短。Feature 工作先收敛到该 Feature 的集成分支；整体验收与
    需要的发布授权完成前，不默认合入主干。
  - 大改用**特性开关 + branch-by-abstraction** 保持短命,不开长命分支攒合并债。
- **B 分叉型(客户定制 / 私有部署 / 长期维护版 / 上游 fork)= 长命是设计,不是失误**
  - ① **能用配置+扩展点表达就别 fork**(同一制品+私有配置,见 `deployment-patterns §7`)。分叉是最后手段。
  - ② 必须分叉则**压小 delta**、把定制隔离进清晰模块/overlay。
  - ③ 同步**单向 核心→变体**;某条定制变通用 → **提升回核心**(走一次普通短命特性)再从变体删。
  - ④ 明确 owner + 支持周期(EOL),只收 backport,不攒新特性。
- 反模式:用长命分支代表环境(改用配置晋级,见 `deployment-patterns §1`);收敛型分支活太久。
- 判据:`要并回主干 → A;不并/不能 → B`。

## 2. 分支命名

- 形如 `<type>/<summary>`,type 取 `feature/fix/hotfix/chore/refactor/docs`(推荐默认;项目可自定但**一仓内统一**)。
- 分支 type 与提交 type **别混**(分支 `feature/`,提交 `feat:`)。

## 3. 提交信息

- Conventional Commits:`<type>(<scope>): <subject>`;中文 subject 允许。
- 有外部消费者的制品用 SemVer(版本/制品规范见 `deployment-patterns`)。

## 4. worktree —— 按需,不是默认

worktree 解决的是"**同时进行且互不干扰**"。没有并行需求就**别开**,普通分支够用。

- **该开**:并行多个**真正独立**的工作(多特性 / 多 agent 同时干);一个长任务想与主线隔离;需同时检出两分支对比联调。
- **不必开**:小修一次性改、串行单线、与在飞改动碰同一批文件的紧耦合、磁盘/配额紧。
- **审慎**:并行有隐性成本——隔离的 agent 各自做**隐式决策、会冲突**。默认少开、能单线就单线。
- 开了就守:一任务一分支一目录、命名 `<repo>-<purpose>`、**各跑各的 DB/端口**、完事即清理;并发 **3–5 上限**。

开 worktree 命令骨架(git worktree 是稳定原语):
```bash
git fetch origin
git worktree add ../<repo>-<purpose> -b <type>/<summary> <accepted-integration-base>
# 再配本目录独立 .env / DB(或 schema) / 端口；由主 Agent 按 canonical protocol 处理集成。
```

## 5. 并行协作:前置合约(核心)+ 收敛安全网

隔离的 agent 没有共享上下文 → 不在开之前把"怎么对齐"定死,各方会做出**局部合理、彼此不兼容**的选择(上下文对不齐)。**省事在前置,后置只是兜底。**

### 5.1 前置：开 worktree 之前确定

- **独立性测试**:只对**真正独立**的子任务开并行;B 依赖 A → 串行(并行只会变成带额外开销的串行)。
- **先确定契约**：agent 间共享的接口、schema 和事件契约先写入共同上下文，作为各方单一事实源；跨边界检查见 `roles/architect`。
- **面切分 + 文件归属**:谁动哪些模块/文件**不重叠**;"无主之地"显式归谁。会碰同一批文件 → 别并行。
- **同一基**:都从同一已接受的 Feature 集成 commit 切。
- **自包含简报 + 显式边界**:主 Agent 按 canonical protocol 给每个执行者完整目标、范围、接口、写集、依赖、验证与结果要求。
- **决策落共享记忆**:产品判断写入产品上下文，工程判断写入 Feature 研发上下文，不靠 agent 互相“看见”。

### 5.2 实施中

- 保持短命、聚焦本面;每个已接受集成节点后同步当前 Feature 集成 commit，让漂移小、冲突早暴露而非攒到最后。
- 越界即停:发现必须动别人那一面 → 前置合约破了,**先改合约,别私改**。

### 5.3 后置:收敛安全网(残余漂移兜底)

即便有合约,基线仍会动。**收敛是串行的**:每次合并都改变其余分支的目标基。

- **串行收敛**：先合入 Feature 集成分支，一次一个，不并发集成。
- **★先基到最新 + 重测,才合**:合 B 前把 B 重基到含 A 的当前 Feature 集成 commit、**重跑完整必要验证**，再合。这条防 merge skew：孤立看兼容、合进更新后的基线就坏。
- **合后跑全量**:抓语义冲突（文本无冲突不等于正确）。
- **冲突在 Task/特性分支里解**，保持集成分支可验证。
- **生成物不手合**:lockfile / 生成客户端 / 快照 → 取一边后**重新生成**,别逐行合噪音。
- **迁移对齐**:加法式(expand)迁移对顺序不敏感(见 `deployment-patterns §3`)。
- **收尾清场**:Feature 整体通过验收且取得所需发布/合并授权后，才按项目策略合入目标分支；随后删分支、
  `git worktree remove`、`prune` 和拆隔离资源。

合并命令骨架:
```bash
# 1) worktree 内:基到当前 Feature 集成分支,在本分支解冲突
git fetch origin && git rebase <feature-integration-branch>
# 2) 重跑完整必要验证（相对当前集成基线）
# 3) 串行合入 Feature 集成分支；其余在飞分支随后重基到该新集成 commit
# 4) Feature 总体验收通过且取得发布/合并授权后，才按项目策略合入目标分支
# 5) 清场
git worktree remove ../<repo>-<purpose> && git branch -d <type>/<summary> && git worktree prune
```

> 有 CI 时，§5.3 的“先基+重测”可由 merge queue 自动化；无 CI 则作人工纪律。它不替代主 Agent 的
> integration acceptance，也不授予主干合并权限。

### 5.4 多 agent Task 分支协议

- 只把依赖已完成、写集不重叠、接口已确定、环境可隔离的 Task 并行化；否则串行。
- Task 分支是可选隔离手段，不是默认要求。使用时一项独立 Task 对应一个分支和唯一负责人。
- 每个执行者收到 canonical protocol 要求的完整 current brief；Task 分支不是简报、结果或状态的额外存储位置。
- 执行者只修改授权范围；发现需要越界或接口不明确时停止并回报，不自行扩大范围。
- 执行者不直接编辑 `state.json`，也不与其他执行者同时写 Feature 研发上下文；返回代码 diff、实际测试和未解决问题，由 Feature 负责人合并。
- Feature 负责人串行集成 Task 分支。每合入一个分支，其余待集成分支先同步最新集成 commit。
- 每次集成后运行受影响测试；全部 Task 集成完成后，在最新集成 commit 上重新运行 Feature 的完整必要验证。
- 并行条件失效时切回串行，保留已有 Task ID、分支和结果。

标准角色评审按改动范围和风险选择；不强制额外的多轮对抗复审。

---

一句话：**先定合约，满足独立条件才并行；先串行集成到 Feature 分支并重测，再在验收与授权后合入目标分支。**
