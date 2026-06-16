# Spec: EVOLUTION 条目挂需求树源叶（Retire 顺带写 `## sdlc 记录`）

> Date: 2026-06-16
> Status: approved
> Target surface(s): backlog 工具（scripts/backlog.py retire + skills/sdlc-backlog）
> Active roles (anticipated): skill-maintainer (R10), qa
> Validate modes (anticipated): correctness

## 1. 问题 / 目标

特性退场（Retire）时，蒸馏出的耐久教训只 append 进 `.sdlc/EVOLUTION.md`（一条扁平流水）。若该特性源自需求树某片叶（`source-leaf`），这条教训和那片叶**失联**——需求树记不住"这片需求 ship 时学到了什么"。

目标：Retire 标源叶 `shipped` 时，把同一条 evolution entry **顺带追加进该源叶 `.md` 的 `## sdlc 记录` 段**，使 `.sdlc/requirements/` 需求树成为**带 sdlc 记录的活档案**——每片叶随身携带它历次被 sdlc 处理后的耐久结论。

## 2. 非目标（YAGNI）

- ❌ 不改 `EVOLUTION.md` 现有行为（仍是唯一正屋流水，照常 append）——本特性是**额外**在叶上挂一份，不替代。
- ❌ 不挂到 frontmatter（演进是 append 流水，归正文段，不是有界标量字段）。
- ❌ 无 `source-leaf` / 叶未命中 / 无 entry → **不挂**（优雅降级，= 今天行为）。
- ❌ 不加 CLI 参数（复用 `--leaf`/`--req-root`/`--evolution-entry`）、不加顶层 skill、不动 stage 枚举。
- ❌ 不做"历史 EVOLUTION 条目回填到叶"（只管今后退场；存量不追溯）。

## 3. 现状摘要（Explore 产出）

- **代码**：`scripts/backlog.py`
  - `_mark_leaf_shipped(req_root, leaf_id)` → 找叶、`_set_frontmatter_status(path, "shipped")`、返回 **bool**。
  - `_append_evolution(sdlc_dir, entry)` → append `EVOLUTION.md`（缺则建 `# Evolution log` 头）。
  - `cmd_retire`：①归档 ②（`--leaf`+`--req-root`）标 shipped ③（`--evolution-entry`）append EVOLUTION ④清栈；**archive 已存在则拒覆盖**（幂等闸）。
- **叶 schema**（SKILL §1.2）：frontmatter 10 字段 + 正文 `## 需求描述`/`## 验收线索`/`## 老系统行为参照`。
- **EVOLUTION 条目格式**：`- <date> · <slug> · <蒸馏教训> · → archive/<date>-<slug>/`。
- **测试**：`scripts/test_backlog.py` `RetireTest`（归档/标 shipped 解锁/回流 EVOLUTION/兜底/幂等拒覆盖/无叶降级）。
- **现状缺口**：标 shipped 与 EVOLUTION append 各自独立，二者不交叉——叶上没有任何 sdlc 处理痕迹。

## 4. 方案与决策

**方案（选定）**：`cmd_retire` 在**源叶命中且有 evolution_entry** 时，把同一条 entry 追加进该叶 `## sdlc 记录` 段。

- `_mark_leaf_shipped` 改为**返回叶绝对路径或 None**（替代 bool；调用处 `leaf_shipped = path is not None`）。
- 新增 `_append_leaf_sdlc_log(leaf_path, entry)`：把 entry append 到该叶文件的 `## sdlc 记录` 段（段不存在则在文件末尾建 `\n## sdlc 记录\n\n` 再写 entry；仿 `_append_evolution` 的"缺则建头"）。
- `cmd_retire`：`leaf_path = _mark_leaf_shipped(...)`；若 `leaf_path and args.evolution_entry` → `_append_leaf_sdlc_log(leaf_path, entry)`，结果入 JSON `leaf_evolution`。

**命名决策**：叶内段名 = **`## sdlc 记录`**（用户指定，具体不抽象，胜过"演进史"）。

**被否**：① 挂 frontmatter 字段——append 流水不属有界标量，否。② 在叶里只写精简版（去 `→ archive` 指针）——保留原文指针更利溯源（叶 ↔ 完整归档双向可达），否。

**范围姿态**：HOLD（刚好做完闭环，不扩）。

## 5. 设计

### 5.1 改动点（scripts/backlog.py）

```
_mark_leaf_shipped(req_root, leaf_id) -> str|None   # 改：返回命中叶的绝对路径（未命中 None）
_append_leaf_sdlc_log(leaf_path, entry) -> None     # 新：append entry 到叶的 `## sdlc 记录` 段（缺段则建）
cmd_retire:
    leaf_path = _mark_leaf_shipped(req_root, leaf) if (leaf and req_root) else None
    leaf_shipped = leaf_path is not None
    if leaf_path and evolution_entry:
        _append_leaf_sdlc_log(leaf_path, evolution_entry)
    # JSON 输出加 "leaf_evolution": leaf_path（挂了）/ None（没挂）
```

`_append_leaf_sdlc_log` 逻辑：读叶文本；若不含 `## sdlc 记录` → 末尾补 `\n## sdlc 记录\n`；在该段下 append `entry + "\n"`。纯标准库，单写者（retire 独占该时刻）。

### 5.2 数据流

```
driver 检测 stage==done → cmd_retire(--leaf L --req-root R --evolution-entry E)
  → _mark_leaf_shipped → 找到 L 的叶文件 path，status:=shipped
  → _append_leaf_sdlc_log(path, E)  # 同 E 也进 EVOLUTION.md（步骤③不变）
  → 叶文件现含 status:shipped + 「## sdlc 记录」下一行 E
```

### 5.3 错误处理 / 降级 / 幂等

- 无 `--leaf` 或叶未命中（`leaf_path is None`）→ 不挂叶，仅 EVOLUTION（今天行为）。
- 无 `--evolution-entry` → 不挂叶（标 shipped 照常）。
- 幂等：retire 的 archive-exists 守卫阻止整体重跑 → 段内单次追加，不重复。
- sdlc-pilot 自身无 `.sdlc/requirements/` 树 → 永不触发挂叶（本特性自己的退场也不会挂，符合预期）。

### 5.4 测试策略（correctness / qa）

`RetireTest` 新增/改：
- **挂叶正路径**：建 req 树 + 叶 + `--leaf`+`--req-root`+`--evolution-entry` → 退场后叶 `.md` 含 `## sdlc 记录` + 该 entry，且 `status: shipped`。
- **无 entry 不挂**：给 `--leaf` 但不给 entry → 叶标 shipped、无 `## sdlc 记录`。
- **无叶降级**：不给 `--leaf` → 仅 EVOLUTION 写，无叶被动（既有 graceful 用例覆盖，确认仍绿）。
- **二次 append 形态**（可选）：叶已含 `## sdlc 记录` 段时再写 → 追加到段内、不重复建段头。
- 既有 `RetireTest` 用例（`_mark_leaf_shipped` 改返回类型后）确认 `leaf_shipped` 语义不变、全绿。

## 6. 怎么算 done（前置验收）

- [ ] `_mark_leaf_shipped` 返回路径/None；`cmd_retire` 在叶命中+有 entry 时把 entry 写进叶 `## sdlc 记录`。
- [ ] 叶 `.md` 同时有 `status: shipped` 与 `## sdlc 记录` + entry；EVOLUTION.md 仍照常 append 同条。
- [ ] 无叶 / 无 entry → 不挂（降级），既有 RetireTest 全绿。
- [ ] cmd_retire JSON 输出含 `leaf_evolution`。
- [ ] `python3 scripts/test_backlog.py` 全绿；`bash scripts/validate-skills` PASS。
- [ ] `sdlc-backlog/SKILL.md §6` Retire 步骤②说明挂叶 + 顶部 op 描述更新。

## 7. Eval 契约
N/A — 不触及 AI/模型/策略。

## 7b. 设计契约
N/A — 无 UI/前端面。

## 8. Deferred Ideas

- **历史 EVOLUTION 回填到叶**
  - Why：本特性只管今后退场；存量 EVOLUTION 条目（如已退场的几个特性）没挂回对应叶。
  - Trigger：若需要需求树完整携带全部历史 sdlc 记录时。
  - 线索（去哪找细节）：EVOLUTION.md 条目带 `→ archive/<slug>/`，可从 archive 的 STATE.source-leaf 反查叶；但多数历史特性 source-leaf=(none)，回填面有限。

## 9. Canonical refs

- `scripts/backlog.py`（`_mark_leaf_shipped` 改签名、新 `_append_leaf_sdlc_log`、`cmd_retire`）
- `scripts/test_backlog.py`（`RetireTest`）
- `skills/sdlc-backlog/SKILL.md`（§6 Retire 步骤② + 顶部 op 描述）
- `.sdlc/EVOLUTION.md`（条目格式参照，行为不变）
- `CLAUDE.md` 迭代表「加/改 backlog 派生操作」（同步指引）
