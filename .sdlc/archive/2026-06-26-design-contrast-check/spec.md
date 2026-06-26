# Spec: design-contrast-check（自研 WCAG 对比度静态校验脚本）

> Date: 2026-06-26
> Status: approved
> Target surface(s): scripts-core（新 python 脚本）+ skill-prose（design 角色卡接入）
> Active roles (anticipated): skill-maintainer, design, qa
> Validate modes (anticipated): correctness

## 1. 问题 / 目标

`design` 角色卡的 a11y 检查里，"颜色对比 ≥ WCAG AA" 现在是 **B 腿 `[render]`**（需起浏览器、靠 zai-mcp-server / 人工目检）或纯 LLM 主观判断。缺一个**确定性、可机器判定、无需浏览器**的对比度校验。

目标：自研一个纯 python3-stdlib 脚本，**静态解析项目 DESIGN.md 里的颜色 token，算 WCAG 2.1 对比度，标出 <AA 的前景/背景组合**。把对比度检查从 B 腿 `[render]` 降为 A 腿 `[diff]`（无需起页面）。

## 2. 非目标（YAGNI）

- ❌ 不引入官方 `@google/design.md` CLI（复审否决：alpha 格式 + node_modules 供应链不入放行路径；官方 lint 对本族「散文 + `:root` CSS 变量」DESIGN.md 覆盖=0）。
- ❌ 不给 DESIGN.md 加 YAML front matter（复审否决：双写违反单一事实源）。
- ❌ 不把对比度校验当**强制必要条件**（只做 advisory；design 卡"以 DESIGN.md 为准，无则退回通用原则"二值语义不变）。
- ❌ 不做完整 a11y 审计（键盘/焦点/reduced-motion 仍归 design 卡 B 腿）；本脚本只管对比度。
- ❌ 不渲染、不截图、不跑浏览器。

## 3. 现状摘要（Explore 产出）

- **代码现状**：`scripts/backlog.py`（739 行，逼近 800 上限）是现有 stdlib 脚本范式——argparse + `json.dumps(ensure_ascii=False, indent=2)` 出 stdout、错误走 stderr。新脚本**独立文件**，不塞进 backlog.py。
- **测试现状**：`scripts/test_backlog.py`（unittest + subprocess + 直接 import 函数）是 TDD 范式，新脚本配套 `scripts/test_contrast_check.py`。
- **接入点现状**：`design` 角色卡的 validate-mode playbook 内嵌在 `references/roles/design.md`（行 88-148）；a11y 硬门已声明"对比 < AA → FAIL"，B 腿 `[render]` 写"查颜色对比（可借 zai-mcp-server / 自动 a11y 检查）"。本脚本即补这个"自动检查"的 A 腿静态实现。
- **真实输入样本**：`sdlc-pilot/DESIGN.md`（`:root{--bg:#f6f1e6;--ink:#1f2d24;--green:#6f925f...}` + status/priority 表格语义色）、`traffic-domain/DESIGN.md`。

## 4. 方案与决策

**脚本** `scripts/contrast_check.py`，纯 python3 stdlib。三段：解析 → 配对 → 算对比度 → 出 JSON。

**配对策略（核心决策，复审 finding M-3 + 用户定）= 启发式跨类 + 可选注释覆盖**：
- **启发式跨类**：按 token 名分两类——
  - 前景类：名含 `ink / text / fg / foreground / muted / label / heading / body / on-`（如 `on-primary`）。
  - 背景类：名含 `bg / background / panel / surface / canvas / base / paper`。
  - 只比 **前景类 × 背景类** 跨类对（不比前景×前景、背景×背景，避免笛卡尔积噪声）。
  - 既不属前景也不属背景的 token（如 `--green / --line / --danger` 语义色）→ 视为"可前景"，与所有背景类配对（语义色 on 背景是真实关心的——复审 M-3 点名的盲区）。
- **可选注释覆盖**：DESIGN.md 里可写一行 `<!-- contrast: ink on bg, green on panel, on-primary on green -->`。**一旦出现该注释，完全改用注释指定的对**（启发式让位）。注释是 advisory 可选输入，不强制、不破坏单一事实源、不是 YAML schema。

**颜色格式支持**（stdlib 能精确算的）：`#RGB`、`#RRGGBB`、`rgb()/rgba()`。**`oklch()/lab()/hsl()` 等**：stdlib 无法无依赖精确转 sRGB → **跳过该 token 并在输出里诚实标 `skipped: unsupported-color-space`**（不假装算过——复审"诚实门"）。

**对比度算法**：WCAG 2.1 相对亮度（sRGB → 线性化 → 0.2126R+0.7152G+0.0722B）+ 对比度 `(L1+0.05)/(L2+0.05)`。

**阈值/分级**（advisory）：
- 对比度 < 3.0 → `severity: warning`（连大字号 AA 都不过）。
- 3.0 ≤ 对比度 < 4.5 → `severity: warning`（正文 AA 不过，大字号 AA 过）。
- ≥ 4.5 → 不报（或 `--verbose` 时 info 汇总）。
- 解析层问题（无 `:root`、坏 hex、不支持色彩空间）→ `severity: info`。

**退出码（非强制必要条件）**：**默认 exit 0**（advisory，无论有无低对比度）。提供 `--strict` 开关：有 <4.5 时 exit 1（供未来想强制的项目自选，本族默认不开）。

**CLI**：`python3 scripts/contrast_check.py <DESIGN.md路径>`（或 `-` 读 stdin）；`--format json|text`（默认 json）；`--strict`。

**对抗性自我证伪（§2.5）**：
- "启发式分类不准怎么办？" → 注释覆盖兜底；且分类不准只影响"比哪些对"，不影响"算得准不准"（算法对已配对的色是确定的）。漏判由注释补，误报是 advisory 可忽略。
- "oklch 跳过会不会让人以为全过了？" → 输出显式列 skipped + 数量，诚实门挡住"虚假全过"。
- "advisory 没人看怎么办？" → 接进 design 卡 A 腿，review 时自动跑、findings 进 `review/design.md`；非强制但默认可见。

## 5. 设计

**模块结构**（`contrast_check.py`，目标 <250 行）：
```
parse_colors(text) -> dict[name,str]        # 提 :root 变量 + 表格 --token #hex
parse_overrides(text) -> list[(fg,bg)]|None  # 提 <!-- contrast: ... --> 注释
classify(name) -> 'fg'|'bg'|'either'         # 启发式分类
to_rgb(color) -> (r,g,b)|None                # #hex/rgb() → RGB;不支持→None
relative_luminance(rgb) -> float             # WCAG 线性化
contrast_ratio(c1,c2) -> float               # (L1+.05)/(L2+.05)
build_pairs(colors, overrides) -> list[(fg,bg)]  # 注释优先,否则启发式跨类
lint(text) -> {findings, summary, skipped}   # 主入口,返回结构化 dict
main()                                        # argparse + json.dumps/text + exit code
```
- **不可变**：纯函数返回新对象，不就地改（PROFILE 约定）。
- **错误处理**：坏 hex / 不支持色彩空间 → 进 skipped 列表 + info finding，不抛异常（永不 crash，像 backlog.py 一样把问题当数据返回）。
- **输出 schema**（JSON）：
  ```json
  {
    "findings": [{"severity":"warning","fg":"ink","bg":"bg","ratio":2.31,"message":"ink(#1f2d24) on bg(#f6f1e6) = 2.31:1, 低于 WCAG AA 4.5:1"}],
    "skipped": [{"token":"accent","value":"oklch(...)","reason":"unsupported-color-space"}],
    "summary": {"pairs_checked": 12, "warnings": 1, "skipped": 1, "pairing": "heuristic|override"}
  }
  ```

**测试策略**（`test_contrast_check.py`，unittest）：
- 正路径：已知对比度色对（黑#000 on 白#fff = 21:1 过；#777 on #fff ≈ 4.48 < 4.5 报）。
- 配对：启发式跨类只配前景×背景；注释覆盖优先于启发式。
- 解析：`:root` 变量提取；表格 `--token #hex` 提取；`#RGB` 短写展开。
- 负路径（qa）：无 `:root`（info，不 crash）；坏 hex（skipped）；oklch（skipped + 诚实标注）；空文件。
- CLI：subprocess 跑真实 sdlc-pilot/DESIGN.md，确认 exit 0（默认）/ `--strict` 行为 / JSON 合法。

## 6. 怎么算 done（前置验收）

- [ ] `scripts/contrast_check.py` 存在，纯 stdlib，`python3 -c "import ast; ast.parse(open(...).read())"` 通过。
- [ ] `python3 scripts/test_contrast_check.py` 全绿（正路径 + 配对 + 解析 + 负路径 + CLI）。
- [ ] 对真实 `sdlc-pilot/DESIGN.md` 跑出合法 JSON，正确识别 ink-on-bg 等低对比对（若有）。
- [ ] `bash scripts/validate-skills` 仍 PASS（design 角色卡引用脚本后无断链/孤儿）。
- [ ] design 角色卡 validate-mode playbook A 腿 + 检查清单引用了脚本（防孤儿），标 distilled-from/updated。
- [ ] CHANGELOG + 版本号同步（minor：加能力）。
- [ ] 退出码默认 0（advisory）；`--strict` 才 exit 1。

## 7. Eval 契约（仅 AI/模型/策略工作）
N/A —— 纯确定性脚本，无 AI/模型/策略面。

## 7b. 设计契约（仅 UI/前端工作）
N/A —— 脚本自身无 UI；它是*检查* DESIGN.md 的工具，不产出 DESIGN.md。（active roles 含 design 是"消费者视角"，确保输出对 design 透镜有用，非本特性产 UI。）

## 8. Deferred Ideas（结构化延后）
- **oklch/lab/hsl 精确支持**：Why—现代 DESIGN.md 可能用 oklch（如本族 web 规则示例）。Trigger—某项目 DESIGN.md 大量用 oklch 且 skipped 噪声变高时。Breadcrumbs—需手写 sRGB↔oklch 转换（无 stdlib 支持），或评估是否值得引入单文件纯算法。本次跳过 + 诚实标注。
- **`--strict` 接入某项目强制门**：Why—某些团队想把对比度当硬性必要条件。Trigger—有项目明确要求。Breadcrumbs—脚本已留 `--strict` 退出码，接入只需在该项目 validate 配置里开。

## 9. Canonical refs
- 调研报告：`workspace/20260626-design.md-research/explorer-repo-report.md`
- 知识卡片：`~/Documents/nsync/ai_knowledge/patterns/design-md-ai-design-system.md`
- 复审结论：本特性 STATE Decisions log + doubt-driven 9 findings
- WCAG 2.1 相对亮度/对比度公式：W3C WCAG 2.1 SC 1.4.3
- 接入点：`skills/sdlc/references/roles/design.md`（validate-mode playbook A 腿）
- 范式参考：`scripts/backlog.py`（脚本风格）、`scripts/test_backlog.py`（测试风格）
