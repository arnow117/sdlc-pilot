# Plan: design-contrast-check

> 复杂度 L2（单脚本 + 测试 + 一处接入）。源自 .sdlc/spec.md。

## Phase 1 — 脚本核心（TDD，wave 1）

### task 1.1 — 写失败测试（RED）
- read_first: `scripts/test_backlog.py`（unittest+subprocess 范式）、spec.md §5 测试策略
- action: 建 `scripts/test_contrast_check.py`，覆盖：
  - 算法正路径：#000/#fff=21:1；#777/#fff<4.5 报；#RGB 短写展开
  - 配对：启发式跨类（fg×bg）；either 类（语义色）配所有 bg；注释覆盖优先
  - 解析：`:root` 变量；表格 `--token #hex`
  - 负路径(qa)：无 :root（info 不 crash）；坏 hex（skipped）；oklch（skipped+诚实标）；空文件
  - CLI：subprocess 跑真实 DESIGN.md，exit 0 默认 / --strict exit 1 / JSON 合法
- acceptance_criteria: `python3 scripts/test_contrast_check.py` 运行即失败（脚本未实现，ImportError/AssertionError）

### task 1.2 — 最小实现（GREEN）
- read_first: spec.md §4/§5、`scripts/backlog.py`（argparse/json 输出风格）
- action: 建 `scripts/contrast_check.py`，函数见 spec §5 模块结构；纯 stdlib；永不抛异常（问题当数据返回）
- acceptance_criteria: `python3 scripts/test_contrast_check.py` 全绿；对真实 sdlc-pilot/DESIGN.md 出合法 JSON

## Phase 2 — 接入 + 收尾（depends_on: Phase 1，wave 2）

### task 2.1 — 接入 design 角色卡（防孤儿）
- read_first: `skills/sdlc/references/roles/design.md` 行 88-148（validate-mode playbook）
- action: A 腿检查清单 + 步骤流程 append 一条"静态 DESIGN.md 对比度自检（调 contrast_check.py）"；标 distilled-from/updated
- acceptance_criteria: `bash scripts/validate-skills` PASS；脚本被引用（非孤儿）

### task 2.2 — 版本 + CHANGELOG
- action: minor 升版（加能力 0.17.1→0.18.0）；写 CHANGELOG 条目
- acceptance_criteria: plugin.json + marketplace.json + CHANGELOG 同步；validate-skills PASS
