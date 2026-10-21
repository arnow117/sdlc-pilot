# 可复用的最小状态层

用于无框架、同一 HTML 中切换两端的原型。源码位于 [runtime.js](../assets/shared-state/runtime.js)，配套 [双端示例](../assets/shared-state/example.html) 和 [状态层测试](../assets/shared-state/runtime.test.cjs)。这是本地演示工具，不是服务端数据库或多进程事务。

## API 约定

`PrototypeRuntime.createStore({ createInitialState, reducer, validate })` 创建独立 store：

- `getState()`：读取不可变状态快照。所有页面通过 selector 从此派生数据。
- `dispatch(action)`：调用产品自己的 reducer，校验新状态后统一发布。成功返回 `ok: true`；失败返回 `ok: false` 与错误信息，旧状态保持不变。
- `subscribe(listener)`：状态提交后通知 UI，返回取消订阅函数。
- `reset()`：从 fixtures 重建初始状态，并取消本 store 的待执行任务。
- `schedule(action, delay)`：安排可被重置取消的模拟结果，返回主动取消该任务的函数。用途是演示延迟，不代表网络请求。

以代码实际导出为准，使用前检查现有测试中的调用方式。数据采用 JSON 可表示的普通对象/数组和值；时间使用字符串或数值，不向 store 存 DOM、函数或第三方实例。

## 产品必须自己提供的内容

1. **fixtures**：初始实体与 ID、当前演示日期和必要的异常样例。
2. **reducer**：权限、状态转换、字段边界、重复操作处理；业务规则只维护一次。
3. **validate**：关键不变量，例如可用库存不得为负、一个借阅实例只占用一份库存。
4. **selectors**：列表、详情、汇总、数量和关联记录，从同一状态计算。
5. **业务测试**：调用 UI 使用的实际 reducer/action，验证成功、拒绝和连续操作后的完整结果。

通用 runtime 保证提交边界和重置隔离；它不知道谁能借书、多少钱应入账，也不能替代产品权限和业务校验。

## 在交付物中使用

开发时保持 runtime、领域逻辑、UI、样式与测试分离。需要单文件时把运行代码和样式内联到 HTML，保留 readable 源码；不把测试文件打入产品页面。

示例中的业务只用于展示两个视图读取同一状态，复制时替换领域逻辑。直接沿用已有 React 状态方案时，保留“动作校验 → 提交一个完整新状态 → 派生两端 UI”的原则即可。

一个 store 只在一个页面运行环境内共享。两个独立 HTML 或窗口没有自动联动承诺；跨窗口同步需要额外设计和验证。
