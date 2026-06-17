# Validate 汇总 — #6 工程→backlog 树生成器

> 日期 2026-06-16 ｜ 分支 feat/backlog-tree-generator ｜ modes: correctness + dogfood
> 阶段总判定: **PASS**（correctness PASS；dogfood 强生成+管线证毕；暴露的 playbook 规范化缺口已当场 escalate build 补上 SKILL §2.7「规范化门」并提交→缺口关闭）

## correctness — PASS
- `python3 scripts/test_backlog.py` → 32 测试 OK exit 0（含 LintCrossFieldTest/WriteTreeTest/BoardTest 新增）。
- `bash scripts/validate-skills` → PASS。

## dogfood（真跑 Generate 于 vendor-research）— PARTIAL（强生成 + 找到缺口）
**执行**：读 vendor-research PROFILE.surface-map → 阶段1 归纳 7 功能域(identity/supplier/product/order/settlement/integration/system) → 阶段2 **7 agent 并行**深读各域代码/契约 → 产 **53 片用户故事叶**。
**生成质量（达标）**：
- 主轴=业务能力域，**非 app/package 结构**（✓ spec §6 核心）。
- 叶标题全用户故事「作为<角色>我要<能力>以便<价值>」，**无工程术语**（✓ a2）。
- status 按代码状态推断准：identity/supplier/product/system=shipped/built、order/settlement/integration=captured（与 surface-map "空骨架/半成品/真实" 一致）。
- 4 交叉字段（actor/failure_class/contract_refs/data_owner）已填；域内 depends_on 无环；每域 6-8 叶（≤上限，不碎片）。
- 覆盖 apps/api/modules 全 7 域 + contracts（integration 重点填 contract_refs）+ packages/shared（settlement 引 Money）。
**管线证（真数据）**：identity 域 6 叶 → `write-tree` 落盘 vendor-research/.sdlc/requirements → `lint` **clean** → `board` 渲染**显示 4 交叉字段**（actor×6/failure_class×6/ld-cross）。

## ★ FINDING（dogfood 暴露，escalate 回 build）
fan-out agent 原始输出**不严格合 schema**：
- product：`priority: high/medium`（应 P0-P3 枚举）。
- settlement：`domain_path: "settlement.billing"`（点号，应斜杠 `settlement/billing`）；`new_domain_path` 误填代码路径。
- system：一片 `domain_path: "api-platform"`（单级无子域→orphan）。
lint **正确**会拒这些（门有效）。但 **orchestrator 合并步必须在 write-tree 前规范化**——P4 playbook(SKILL §2.7) 描述了合并(去重/cross_link/无环/上限)但**漏列"字段规范化到 schema"**。
→ 缺口在 **playbook**（非代码 bug；脚本/lint 都对）。escalate build 补 §2.7 一条"规范化门"。

## 门控
- [x] correctness PASS
- [~] dogfood PARTIAL：生成+管线证毕；merge 规范化缺口 → 回 build 补 playbook
- 阶段 = GATED，next → 回 sdlc-build 给 §2.7 加规范化步，再回 validate 确认。
