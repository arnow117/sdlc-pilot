# sdlc-pilot 看板设计

## 当前看板实现与评审范围

当前 `backlog board` 由 [board.py](scripts/board.py) 根据 [backlog.py](scripts/backlog.py) 的只读投影生成自包含 HTML。
数据来自 `.sdlc-v1/state.json`，状态与字段以 [轻量运行时](skills/sdlc/references/lightweight-runtime.md) 为准。

| 方面 | 当前实现 |
|---|---|
| 颜色与主题 | CSS 内联，支持系统浅色 / 深色；实际 token 唯一见 `board.py` 的 `_CSS` |
| 布局 | 按 domain 分组的响应式卡片网格，顶部显示 total、各状态数量及 ready 数量 |
| Requirement | 显示 ID、标题、状态、priority 和产品上下文路径 |
| Feature / Task | 显示 Feature 状态、branch、工程上下文路径，以及 Task 的 ID、状态与标题 |
| 交互边界 | 当前为静态只读展示；没有旧方案中的聊天面板、live badge、搜索、状态筛选或状态回写 |
| 实现边界 | 使用 Python 标准库生成，文本经 HTML escaping；不依赖浏览器框架、网络字体或常驻服务 |

设计评审与适用的真实页面验证按当前卡片、主题、断点和内容检查；原始设计提案不能作为已经实现或已经通过验收的证据。
产品项目的设计方法与 Web / App 验证分别见 [design 角色](skills/sdlc/references/roles/design.md) 和
[e2e 约束](skills/sdlc/references/validate-modes/e2e.md)，不要求沿用本看板的历史视觉主题。

## 0.16.0 历史视觉 / 交互方案

[查看旧版需求树看板设计](docs/specs/board-0.16.0.md)。
