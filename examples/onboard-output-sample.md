# 示例：sdlc-onboard 的项目上下文

> 这是虚构 Web + API 项目 `acme-shop` 的 `.sdlc-v1/project.md` 示例，展示已有源码但测试准备尚不完整的情况。
> 所有路径和事实均为示例设定，不是实际工程的运行证据；真实 Onboard 必须从目标仓库核对后填写。

结构来自 [PROJECT 模板](../skills/sdlc/references/templates/PROJECT.md)。Onboard 记录事实与缺口；Plan 明确验收策略，
Build 准备环境和测试资产，Validate 执行当前 commit 的必要检查。Web / App 工具约束见
[e2e](../skills/sdlc/references/validate-modes/e2e.md)。

~~~markdown
# Project Context: acme-shop

## Purpose

面向消费者的购物站点。Web 负责商品浏览与结算，API 负责商品、订单和库存；输入为用户请求，输出为页面与业务响应。

## Tech stack

| Area | Technology | Why / source |
|---|---|---|
| Runtime | TypeScript、Python | web/package.json、services/api/pyproject.toml |
| Framework | Next.js、FastAPI | 依赖声明与对应源码入口 |
| Storage | Postgres | services/api/db.py；示例项目的关系型存储 |
| External systems | none | 示例项目未配置支付、邮件等外部集成 |

## Entry points

| Purpose | Path or command | Notes |
|---|---|---|
| Start | none | 尚无经过运行验证的启动命令 |
| Web | web/app/layout.tsx | 页面根入口 |
| API | services/api/main.py | 应用与路由注册 |
| Configuration | web/package.json、services/api/pyproject.toml | 依赖与工程配置 |

## Commands

```yaml
commands:
  unit: "none"
  coverage: "none"
  e2e: "none"
  typecheck: "none"
  lint: "none"
  build: "none"
```

当前没有可引用的运行验证结果，不能将依赖名称推断为可用命令。Build 必须核对并实际运行相关入口后刷新此节。

## Validation setup

| Item | Verified setup / source or gap |
|---|---|
| Modes and tools | correctness、e2e:Web、e2e:OpenAPI；Web 必须使用 tester-army/e2e CLI + Web engine，当前尚未安装或固定版本 |
| Test assets | none；尚缺 e2e 配置、已提交测试、fixture / 清理方案；没有共享回放缓存 |
| Target environment | none；启动方式、隔离测试 URL 和被测构建与 commit 的对应关系尚未确认 |
| Model and test identity | none；Plan 尚未选择 provider / model、测试身份与外部凭据来源，不在本文存放凭据值 |
| Run outputs | none；Build 需准备框架报告 / 附件目录、Git ignore 及稳定归档位置；Validate 显式使用只读缓存 |
| CI | none；尚无测试工作流或产物归档 |
| Preparation gaps | 启动、工具版本、测试覆盖、隔离数据、确定性业务断言、模型预算与报告归档均待准备 |

## Surface map

```yaml
surfaces:
  - name: web-frontend
    globs: ["web/**"]
    roles: [client-dev, design]
    modes: [correctness, "e2e:Web"]
  - name: api
    globs: ["services/api/**"]
    roles: [server-dev]
    modes: [correctness, "e2e:OpenAPI"]
  - name: database-migrations
    globs: ["migrations/**"]
    roles: [server-dev, architect]
    modes: [correctness]
```

跨 Web / API 等多个 surface 的改动按 role-routing 补充 architect；命令缺失不免除相应的必要验证。

## Conventions

- 前端设计约定见 DESIGN.md；API handler 负责协议转换，业务逻辑放在 service 层。
- 工程指令见 AGENTS.md；共享或生产环境不执行会修改业务数据的测试。
- project.md 记录项目事实，当前 Feature 的测试策略与运行证据写入其 engineering context。

## Known risks

| Risk | Affected area | Current handling |
|---|---|---|
| 自动化入口和覆盖尚未建立 | web、api | 在 Plan 明确所需检查，Build 准备并验证入口 |
| 结算涉及可变数据 | web、api、migrations | 隔离测试数据与清理方式尚未确定，必要旅程保持未验证 |

## Deployment

```yaml
target: none
config_paths: []
environments:
  dev: none
  staging: none
  canary: none
  full: none
health_check: none
```

尚无部署配置或经过确认的运行环境；实际发布前按目标工程补齐。

## Repository context sources

```yaml
root_guidance: AGENTS.md
scoped_guidance: []
canonical_documents: [README.md, DESIGN.md]
repo_context:
  status: none
  analyzed_commit: none
```

示例设定中上述文件存在；未提供 repo-context 已验证索引。真实工程应按当前 commit 核对路径，只索引文档，不复制正文。

## AI readiness

已有项目指令和清晰的 Web / API 入口；自动化命令、测试发现、构建版本标识与验证环境仍缺失，不能宣称验证通过。
~~~

Onboard 的唯一交付物是 `project.md`；它不安装测试框架，不创建 Requirement / Feature，也不推进 lifecycle state。
缺口补齐后局部刷新本文件，测试配置、测试资产与框架产物仍按目标工程约定存放。
