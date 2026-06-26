# Spec: contrast-prefix-match

> Date: 2026-06-26 · Status: approved · work-type: feature
> Target surface: scripts-core + skill-prose
> Active roles: skill-maintainer, qa · Validate modes: correctness

## 1. 问题 / 目标
happycompany 实测暴露 `contrast_check.py` 两个真实可用性缺口：
1. **注释覆盖要写冗长全名**：token 命名带公共前缀（`--color-text-primary`），注释必须写 `color-text-primary on color-bg-base`，啰嗦易错（实测写短名 `text-primary` → 0 pairs，静默失效）。
2. **大 token 集裸启发式噪声爆炸**：176 对 → 109 warning，真信号（3 个）被淹没。

目标：(A) 注释/匹配支持**前缀归一**——短名 `text-primary` 自动匹配唯一的 `color-text-primary`；(B) 把"大集必注释收窄 + 前缀归一可用短名"写进接入纪律。

## 2. 非目标（YAGNI）
- ❌ 不改启发式分类算法本身（裸跑噪声靠注释收窄，是已定 trade-off）。
- ❌ 不做自动按命名段分组配对（Deferred：算法复杂，注释覆盖已够用）。
- ❌ 不改对比度计算 / 退出码 / 诚实门（稳定，不动）。

## 3. 现状摘要
- `build_pairs(colors, overrides)`：override 时直接返回 `[(fg,bg)]`，下游 `lint()` 用 `if fg not in rgb or bg not in rgb: continue` 跳过找不到的——所以短名静默失效（不报错、不计数）。
- 缺一个"把 override/启发式里的名解析到真实 token key"的归一层。

## 4. 方案与决策
新增 `resolve_token(name, colors) -> str|None`：
1. 精确匹配 `name in colors` → 返回。
2. 否则后缀匹配：唯一一个 token key 满足 `key == name` 或 `key.endswith("-"+name)` → 返回该 key。
3. 多个匹配（歧义）或零匹配 → 返回 None。

`build_pairs` 的 override 分支对每个 `(fg,bg)` 用 `resolve_token` 归一；归一失败的对**丢弃并记一条 info**（"override 名 X 未匹配到 token / 歧义"），不静默吞。启发式分支不变（它本就用真实 key）。

**对抗性自我证伪**：歧义时绝不猜（返回 None + info），避免"短名匹配错 token 给假对比度"。精确名永远优先于后缀匹配（不破坏现有全名注释）。

## 5. 设计
- `resolve_token` 纯函数，无副作用。
- `lint()` 收集 override 归一失败为 `findings`（severity info），summary 不变。
- 文档：`design.md` 接入说明 append 两句——大集用注释收窄；带公共前缀可写短名（前缀归一，歧义会报 info）。

## 6. 怎么算 done
- [ ] `resolve_token` 短名后缀匹配 + 精确优先 + 歧义返回 None，有测试。
- [ ] override 短名 `text-primary` 能匹配 `color-text-primary`（happycompany 场景）。
- [ ] 归一失败的 override 名进 info finding，不静默。
- [ ] 现有 28 测试不回归；新增用例全绿。
- [ ] `bash scripts/validate-skills` PASS。
- [ ] 版本 patch（0.18.0→0.18.1，补能力但向后兼容）+ CHANGELOG。

## 7. Eval 契约 — N/A
## 7b. 设计契约 — N/A（脚本无 UI）

## 8. Deferred Ideas
- **自动命名段分组配对**：Why—彻底消除裸跑噪声而不需注释。Trigger—注释维护成本高到无法忍。Breadcrumbs—需识别 token 命名层级（color-{role}-{variant}），按 role 域内配对。本次用前缀归一 + 注释，够用。

## 9. Canonical refs
- happycompany 评估：`workspace/happycompany/web/src/styles/tokens.css`（176 对 / 3 真问题）
- 脚本：`scripts/contrast_check.py`（build_pairs / lint）
