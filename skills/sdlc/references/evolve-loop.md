# 回流回路(Evolve Loop)—— 时用时新的"改自己并发回 GitHub"

> distilled-from: kb-manage, distillation-loop, session:sdlc-evolve-design-2026-06-06
>
> 这份 playbook 是 **数据,不是 skill**(与 `distillation-loop.md` 并列)。任何引擎(Claude + Read/Edit/Bash/Grep,或 Codex)都能照着执行,不依赖任何运行时工具。
> 由 driver 的 **`/sdlc evolve`** 子命令入口加载。它**复用** `distillation-loop.md` 做"把 pattern 放进哪张卡"(不重写方法论),只补 distillation-loop 不管的:**定位源 + 安全发布闸 + GitHub 回流**。
> 全程以 `skill-maintainer` 角色卡为透镜(防臃肿 / additive / 防孤儿 / 溯源 / 可移植 / semver / 自我修改安全)。

---

## 0. 它解决什么

时用时新的最后一公里:你在**别的项目 X** 里用着 sdlc-pilot,冒出"这套技能该改进 Y"的念头,
evolve 把这个念头**安全地落回 sdlc-pilot 的 git 源、并发回 GitHub**。

核心认知(决定为何要人工检查点):用 vN 改出 vN+1,**本次运行始终 vN 掌舵,vN+1 下趟才生效**。
所以一个改动的行为只能下趟验证 → 当前趟的安全网 = lint + additive 守卫 + **人工过目**,不是"现场跑"。

---

## 1. 用 evolve(小改)还是走完整 `/sdlc`(大改)—— 机器可判

evolve **物理上只做 append-to-existing 小改**。落位前先判:

```
若这次落位 = 仅 append/收紧 references/ 下【已存在】的卡  → evolve 放行
若 = 新建文件 / 动 role-routing / driver / STATE 模板 / stage 枚举(契约/结构性)
     → 停,escalate(text_mode):
       "这是结构性改动(新建卡/动契约),不该走 evolve 轻量路。
        请对 sdlc-pilot 仓跑完整 /sdlc(spec→…→ship),含多角色 review。"
```

> 这道 guard 在 §3 闸 B 用 `git diff` 再兜一次:即便判断失误真写了结构性改动,闸 B 也会拦下并回滚。

---

## 2. 主管道(6 步)

```
①捕获 → ②探源 → ③落位 → ④发布闸(§3)→ ⑤回流(§4)→ ⑥回报
```

### ① 捕获
洞察来自**当前 session**(刚才 build/validate/review 里发现的踩坑/缺口)+ 用户一句话描述要改什么。
**不做持久 inbox**(跨机器不可靠)。一次 evolve 聚焦**一个**改进。

### ② 探源(定位可写的 sdlc-pilot 源)—— 见 §5
按序探:`readlink ~/.claude/skills/sdlc` 的目标 → 记录过的 source-path → 都没有则**只剩只读插件缓存**,
停下,text_mode 引导用户先 clone(owner)或 fork(第三方),给出命令。**绝不在只读缓存上改。**

### ③ 落位(复用 distillation-loop)
`cd` 到源,按 `distillation-loop.md` §2-③/④/⑤ 的两轴定位写进对的卡(角色/模式/语言/阶段),
additive 合并、标 `distilled-from` 与 `updated`。**这一步不重写方法论,直接照 distillation-loop 做。**

### ④ 发布闸
见 §3(临时分支 → lint → additive 守卫 → 升版本/CHANGELOG → 人工检查点)。

### ⑤ 回流
见 §4(owner 合 main 直推 / 第三方 fork+PR)。

### ⑥ 回报(text_mode)
告诉用户:改了哪张卡、版本号、commit sha /(第三方)PR 链接。

---

## 3. 安全发布闸(自我修改的四层兜底)

```
①(在源)开临时分支:  git switch -c evolve/<topic>     # 绝不直接动 main 工作区
② 应用 ③ 落位的 append 改动
③ 闸 A 结构 lint:      bash scripts/validate-skills    # 断链/孤儿/frontmatter/交叉引用全过
④ 闸 B additive 守卫:  git diff --stat / --name-only 自检——
      只动 references/ 下已存在卡、只见新增行、无意外删除、无新建文件、未碰 role-routing|driver|STATE模板|枚举
      → 任一不满足:判为结构性 → 自动回滚(§ 回滚)+ escalate 走完整 /sdlc
⑤ 升版本 + CHANGELOG:  补内容=patch / 加能力=minor(改 plugin.json + marketplace.json + 写一条 CHANGELOG)
⑥ 闸 C 人工检查点(text_mode):把 diff + 版本 + CHANGELOG 摆给用户,等确认
      1) 确认,发布   2) 我要再改   3) 放弃(回滚)
```

**回滚**(任一闸挂 / 用户放弃):
```
git restore . ; git switch main ; git branch -D evolve/<topic>
```
源回到干净 main,坏改动**进不了 main、进不了 GitHub**。一次 evolve = 一聚焦改动 = 一 commit + 一次升版本 → 真出问题 `git revert` 或把插件降回上一版本号即回滚。

四层安全:**范围闸**(§1)+ **临时分支/回滚** + **人工检查点(闸 C)** + **原子可逆**。

---

## 4. GitHub 回流(探权限自适应)

闸 C 通过 → 在临时分支 commit → 探对 upstream 的推送权,二选一:

```
owner(对 upstream 有写权):
  git switch main && git merge --ff-only evolve/<topic> && git push origin main
  (不走 PR;安全已由闸 C 人工过目 + 临时分支回滚兜住)

第三方(无 upstream 写权):
  git push <fork> evolve/<topic>
  gh pr create --repo <upstream> --base main --head <fork>:evolve/<topic>  # 起草 PR 回上游
```

- 怎么判 owner vs 第三方:试探 upstream 推送权(如 `git push --dry-run origin` 成功 = owner;失败/无权 = 第三方)。
- **无 `gh` 的环境**(纯 Codex)且为第三方:不假装已提 PR,改为打印手动建 PR 的步骤 + 比较 URL(`https://github.com/<upstream>/compare/main...<fork>:evolve/<topic>`)。
- **密钥**:全程不读不写任何密钥;push/PR 靠用户本机已有的 git/gh 凭据。

---

## 5. 探源细节(②)

```
1) readlink -f ~/.claude/skills/sdlc  或  ~/.codex/skills/sdlc  2>/dev/null
     → 两个都试(Claude Code 装在前者、Codex 装在后者;owner 常两者都软链到同一源)。
     → 指向一个真实 git 仓(含 .claude-plugin/plugin.json)= 软链安装的源,用它。
2) 否则读记录过的 source-path(如用户 ~/.sdlc-pilot-source 或 git config 里的约定项)。
3) 否则定位到只读缓存(~/.claude/plugins/cache/.../sdlc-pilot)= 不可写:
     停,text_mode:
       "没找到可写的 sdlc-pilot 源 clone。先:
          owner →  git clone git@github.com:<you>/sdlc-pilot.git ~/code/sdlc-pilot
          第三方 → 先 fork,再 clone 你的 fork
        然后重跑 /sdlc evolve(我会记住这个路径)。"
```

> 找到可写源后,确认它在干净状态(`git status` 无未提交无关改动);脏树则先提示用户处理,**不把 evolve 改动和无关改动混在一起**。

---

## 6. 与其他源的配合(一句话)

- `distillation-loop.md` 提供 **③落位** 的方法论(放进哪张卡 / additive 合并 / 溯源 / 防孤儿)——evolve 复用,不重写。
- `skill-maintainer.md` 角色卡提供**全程透镜**(防臃肿 / 可移植 / semver / 自我修改安全的判据)。
- 本 playbook 只增量贡献 distillation-loop 不管的:**探源 + 安全发布闸 + GitHub 回流**。
