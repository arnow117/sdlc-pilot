# 设计:sdlc-evolve —— 时用时新的自更新回流能力

> Date: 2026-06-06
> Status: approved
> 形态结论:**不新增顶层 skill**。用「角色卡 + playbook + 驱动入口」表达(两轴模型)。
> 上游设计:`docs/specs/2026-06-03-sdlc-pilot-design.md`(主设计);复用 `references/distillation-loop.md`(蒸馏方法论)。

---

## 1. 问题 / 目标

sdlc-pilot 的核心承诺是**时用时新**:用着用着发现可改进处,能把改进沉淀回工具并发布回 GitHub。
现状有方法论(`distillation-loop.md` 管"把 pattern 放进哪张卡")、有维护契约(CLAUDE.md)、有 lint、有版本纪律,
但**缺一座桥**:从"在**别的项目 X** 里用着、冒出改进念头"→ 到"改进真正落回 sdlc-pilot 的 git 源并 push/PR 上 GitHub"之间没有可执行回路。

目标:补上这座桥,且让"工具改自己"这件**本质有风险**的事变得安全、可回滚、有人工检查点。
同时让**其他用户**(不拥有 upstream 仓)也能时用时新(经 fork + PR)。

## 2. 非目标(YAGNI)

- 不做持久"改进 inbox"/异步攒洞察(跨机器/跨 session 不可靠;v1 用"显式调用 + 当前 session 洞察 + 用户一句话描述")。
- 不做行为级自动回归测试纯文本卡片(诚实:纯 prose 改动靠 lint + additive 守卫 + 人工过目,不假装有单测)。
- 不让 evolve 处理结构性/契约性大改(那走完整 `/sdlc`,见 §4 边界)。
- 不新增顶层 skill(铁律 #1 原样保住)。

## 3. 关键认知(决定设计形态)

### 3.1 用 vN 改出 vN+1(自举)
执行 evolve 时,**当前 session 加载的是 vN 的技能内容**(skill 在调用开始即读入内存)。
evolve 编辑源 → 产出 vN+1 的卡片。**本次运行自始至终是 vN 在掌舵**;vN+1 要到**下一次调用**才生效:
- 软链安装 → 下个 session 自动生效(软链直指源)。
- 插件安装 → 需 `/plugin marketplace update` 拉取。

推论:
- **安全特性**:跑到一半不会"换掉自己"——不会自我 rug-pull。
- **验证天然滞后**:一个改动的"行为对不对"只能在**下一趟**验证 → 所以当前趟的安全网必须是
  lint + additive 守卫 + **人工检查点**,而非"现场跑一下"。
- **飞轮**:vN 能改进 vN(含改进 evolve 自己),时用时新是复利的。

### 3.2 两轴拆解(决定"不加 skill")
按本项目两轴模型(Roles=视角/知识,Skills=流程/动作)拆 evolve:

| 成分 | 轴 | 落点 |
|---|---|---|
| 维护者**视角**:防臃肿、additive 合并不覆盖、防孤儿/断链、溯源 distilled-from、可移植铁律、semver、自我修改安全 | 知识 | **新增角色卡** `roles/skill-maintainer.md` |
| 6 步**管道 + 安全闭环**:探源、临时分支、lint+additive 守卫、升版本/CHANGELOG、owner-PR/第三方-fork+PR、回滚 | 流程 | **`references/evolve-loop.md` playbook**(与 distillation-loop 并列的数据) |
| **入口** | 驱动 | driver 的 **`/sdlc evolve`** 子命令 |

知识进了角色卡后,"独立 skill"变得不必要:大改走完整 `/sdlc` + 该卡作透镜;小改走 `/sdlc evolve` + playbook。
**铁律 #1 不动**,与项目其它所有扩展方式(references + 路由,从不新增 skill)一致。

---

## 4. §1 身份与 scope 边界(防臃肿阀)

**一句话**:sdlc-evolve 是让 sdlc-pilot **改进自己并发布回 GitHub** 的轻量回路;只作用于工具自身,不碰任何目标项目。

**小改 vs 大改 —— 机器可判定,非凭感觉**:

| 维度 | 小改 → `/sdlc evolve` | 大改 → 对 sdlc-pilot 跑完整 `/sdlc` |
|---|---|---|
| 判据(可查) | 只 **append/收紧已存在的卡**;不新建文件、不动 role-routing / driver / STATE 模板 / stage 枚举 | 新建卡(角色/模式/语言),或动路由/枚举/driver/模板 |
| 设计审批 | 不需(意图自明) | 需(spec HARD-GATE) |
| 阶段 | 捕获→落位→闸→回流(单趟) | onboard→spec→plan→build→validate→review→ship |
| 协调文件 | 1 张卡 | 4–5 处同步(CLAUDE.md 怎么迭代表) |
| 版本 | 多为 patch | minor / major |
| 审查 | lint + 人工过目 | 多角色 review + validate(防 mis-route) |

**guard 有牙(④发布闸前先验)**:
```
git 改动 = 仅改 references/ 下已存在卡   → 放行(小改)
git 改动 = 新建文件 / 动 role-routing|driver|STATE模板|stage枚举
                                        → 停 + 自动回滚 + escalate:
   "这是结构性改动,请对 sdlc-pilot 跑完整 /sdlc。"
```
即 evolve 物理上只做 append-to-existing;碰契约就掀桌让你走完整流程。

> 自举注记:**"造 evolve" 这件事本身按此 guard 判为大改**(新建角色卡 + 动 role-routing + STATE 模板 + onboard 字典),
> 因此它该走完整 `/sdlc` 实现,而非走自己。

## 5. §2 主管道(6 步)

```
①捕获    当前 session 洞察 + 用户一句话描述要改什么(无持久 inbox)
   ↓
②探源    readlink ~/.claude/skills/sdlc → 源 clone;或读记录的 source-path;
         只剩只读插件缓存 → 停,引导先 clone/fork(给出命令)
   ↓
③落位    cd 源 → 按 distillation-loop 两轴定位写进对的卡 + 标 distilled-from(复用,不重写方法论)
   ↓
④发布闸  见 §6 安全闭环(branch → lint → additive 守卫 → 升版本 → CHANGELOG → 人工过目)
   ↓
⑤回流    探对 upstream 推送权:owner / 第三方,见 §7
   ↓
⑥回报    改了哪张卡、版本号、commit/PR 链接
```

## 6. §3 自我修改的安全闭环(四层兜底)

```
① 源 clone 开临时分支(绝不直接动 main 工作区)
② 应用 append 改动(只往已存在卡加)
③ 闸 A 结构 lint:bash scripts/validate-skills 全过
④ 闸 B additive-only 守卫(机器查):diff 只动已存在卡、只见新增、无意外删除、无新建文件、未碰契约文件
      → 不满足:自动回滚 + escalate 走完整 /sdlc
⑤ 闸 C 人工检查点(text_mode):把 diff + 版本 + CHANGELOG 摆出,等用户确认
      → 拒 / 任一闸挂:git restore 回干净 main,源无痕(可回滚)
      → 准:commit → 进 §7 回流
```

四层安全:
1. **范围闸**(§4 guard):只做 append 小改,碰契约掀桌。
2. **临时分支 + 回滚**:任何闸挂,`git restore` 回干净 main;坏改动进不了 main/GitHub。
3. **人工检查点**(闸 C):每次 publish 前必有人过目 diff —— 自我修改永远有人在环。
4. **原子可逆**:一次 evolve = 一聚焦改动 = 一 commit + 一次升版本;出事可 `git revert` 或把插件降回上一版本号。

## 7. GitHub 回流(探权限自适应)

```
探对 upstream 的推送权:
 ├ 有(owner)   → (临时分支已过 §6 闸 A/B/C)合并回 main + 直推 origin main,不走 PR
 │                安全来自 §6 的人工检查点(闸 C)+ 临时分支回滚,而非 PR 评审
 └ 无(第三方)  → push 到自己的 fork + gh pr create 回 upstream
```
- **无 `gh` 的环境**(纯 Codex)且为第三方:降级为打印"手动建 PR"的步骤与 URL,不假装已提。
- owner 直推 main 是有意选择(个人快迭代);自我修改的安全靠闸 C 人工过目 + 临时分支可回滚兜底,不靠 PR。

## 8. 组件与要改的文件(实现清单)

| 文件 | 动作 | 说明 |
|---|---|---|
| `skills/sdlc/references/roles/skill-maintainer.md` | **新增** | 维护者视角:关注点/检查清单/好的样子/常见翻车/介入阶段(防臃肿·additive·防孤儿·溯源·可移植·semver·自我修改安全) |
| `skills/sdlc/references/evolve-loop.md` | **新增** | 6 步管道 + §6 安全闭环 + §7 回流;数据非 skill,任何引擎可执行 |
| `skills/sdlc/SKILL.md` | 改 | 加 `/sdlc evolve` 子命令入口 + 触发语("蒸馏进 sdlc"/"自更新"/"evolve the skills");description 补 evolve 触发 |
| `skills/sdlc/references/role-routing.md` | 改 | 加规则:编辑 `skills/**` · `*SKILL.md` · `.claude-plugin/**` · `references/**` → 上 `skill-maintainer` 透镜;§3 角色字典 + §5 自检登记 |
| `skills/sdlc/references/templates/STATE.md` | 改 | 角色取值字典加 `skill-maintainer` |
| `skills/sdlc-onboard/SKILL.md` | 改 | Phase C 角色字典加 `skill-maintainer`(onboard sdlc-pilot 自身时,skills/** 面路由到它) |
| `scripts/validate-skills` | 改 | 新增角色卡纳入交叉引用检查(自动覆盖,无需特判) |
| `CLAUDE.md` | 改 | "怎么迭代"表加一行"加 meta 能力(evolve)";说明 meta 能力经角色卡+playbook+入口,不新增 skill |
| `README.md` | 改 | 加"时用时新:怎么升级/回流"小节(owner 与第三方两条路径) |
| `CHANGELOG.md` + 版本 | 改 | minor(新增能力);plugin/marketplace version 同步 |

> 不新增:顶层 skill、`.planning/`、运行时依赖。全部增长在 references + 路由,符合反膨胀红线。

## 9. 可移植性

- 交互:闸 C 等所有提问用 text_mode(纯文本编号),不硬依赖 AskUserQuestion。
- 并行:evolve 本质串行(单写源),无需 Task。
- 工具:核心只需 Read/Edit/Bash/Grep + git;`gh` 缺失时回流降级为手动 PR 指引。
- Codex:`.agents/skills/` 软链可发现;evolve-loop.md 是纯数据,任何引擎照跑。

## 10. 怎么算 done(验收)

- `/sdlc evolve` 能从任意项目 X 触发,探到源 clone(readlink/配置),探不到时给出 clone/fork 引导。
- 一次小改全程闭环:开分支 → append → lint → additive 守卫 → 人工过目 → commit → PR(owner)/fork+PR(第三方)。
- 任一闸失败或用户拒绝 → 源回到干净 main,无残留(可演示回滚)。
- 试图做结构性改动 → 被 guard 挡下并 escalate 到完整 `/sdlc`。
- `skill-maintainer` 角色卡被 role-routing 正确触发(编辑 skills/** 时加载);过 lint 防孤儿。
- 全程无密钥入仓;owner 经闸 C 人工确认后直推 main(不走 PR),第三方走 fork+PR。

## 11. 实现路径(照本项目自己的规矩)

本能力本身按 §4 guard 判为**大改** → 实现走**完整 `/sdlc` 流程**(dogfood):
onboard sdlc-pilot 自身 → 本设计作 spec → sdlc-plan 拆任务(多文件同步,见 §8)→ build → validate(lint)→ review(skill-maintainer 透镜)→ ship(发版)。

## 12. Deferred Ideas

- 持久"改进 inbox"(跨 session 攒洞察)—— Why:跨机器不可靠;Trigger:确有高频异步攒需求时;Breadcrumbs:§2①。
- evolve 自动跑轻量 retro 提议改进 —— Why:distillation §1.1 已有 retro 触发;Trigger:retro 与 evolve 想合流时。
- 第三方贡献的"上游接收"侧(PR 模板/CI 校验 lint)—— Why:目前只设计了贡献者侧;Trigger:真有外部 PR 时;Breadcrumbs:§7。
