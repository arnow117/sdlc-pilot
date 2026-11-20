# 可选审阅资产

复杂原型评审用的可选资产。行为约定与适配说明在 [../../references/review-console.md](../../references/review-console.md)；这里是实现与示例。

## 内容

| 文件 | 用途 |
|---|---|
| `review-console.js` | 导览控制器。适配器制，不接触产品私有状态 |
| `review-panel.js` | 可选 DOM 面板。宿主决定挂在哪里 |
| `review-console.test.cjs` | 控制器行为测试 |
| `review-panel.test.cjs` | 面板 DOM 测试（自带最小 DOM，不依赖第三方库） |
| `examples/mobile-parcel.js` | 合成业务：移动端取件 |
| `examples/desktop-ticket-desk.js` | 合成业务：桌面工单台 |
| `examples/parcel-console.html` | 移动端示例页，可直接打开 |
| `examples/ticket-desk-console.html` | 桌面工作台示例页，可直接打开 |

## 用法

```js
const review = PrototypeReviewConsole.createConsole({ adapter: app.adapter });
const panel = PrototypeReviewPanel.createPanel({
  console: review,
  host: document.querySelector("#review-host"),
  title: "审阅台",
});
```

适配器提供 `pages()`、`scenarios()`、`call(name, args)`、`reset()`；观察步骤还需要 `read(name, args)`。产品自管任务用 `cancelPending()` 取消，或声明 `pendingPolicy: "none"`；两者都没有时控制器拒绝重建产品状态并说明原因。

适配器方法同步返回。延迟操作由 `call()` 返回 `{ok: true, pending: true}`，再通过 `read` 和场景检查确认；不要直接返回 Promise。

`cancelPending()` 与 `reset()` 必须返回 `{ok: true}` 才算成功。`false`、`{ok: false}`、`{ok: true, pending: true}`、`undefined`、Promise 一律当作失败，控制器报告失败并跳过产品重置。

面板在 Node 下测试时传入 `document`（见 `review-panel.test.cjs` 里的最小 DOM）。

## 测试

```bash
node --test skills/sdlc-prototype/assets/review-console/review-console.test.cjs
node --test skills/sdlc-prototype/assets/review-console/review-panel.test.cjs
```

## 边界

- 不提供状态快照恢复；回看是从已知起点重放业务动作。
- 不取消产品自管的定时任务，只调用产品的 `cancelPending()`。
- 不保证跨窗口、真实外部请求或生产并发下的行为。
- 不判断业务规则；规则由产品自己的 reducer 与动作实现。
- 场景定义不合规时拒绝开始：未知步骤类型、未知入口类型、没有可执行检查的观察步骤、未知比较方式、缺失的 `read`、观察步骤声明 `expectError`、不可 JSON 序列化的参数都不降级成可信状态。校验在触碰产品状态之前完成。
- 声明了 `expectError` 的步骤必须真的被拒绝**并给出拒绝证据**；没有证据的失败不算预期拒绝，控制器自己的兜底文案不能充当拒绝原因。带 `check` 的预期拒绝步骤在拒绝后还要实际验证这个检查。
- 步骤失败后本次运行停止，需要显式 `reset()` 或 `replayTo()` 恢复。
- 回看只回到本次已走到的步骤，不执行未走过的未来步骤；回看的状态、日志与拒绝原因只来自本次重放；跳过的步骤保留历史、不执行，重新执行要显式调用 `rerun(stepId)`。
- 回看在等待外部结果时自己掌握进度：`next()` 不推进步骤，`refresh()` 手动确认后让它继续，`skip()` 被拒绝；定时确认与手动确认走同一条路。
- 预期拒绝后的 `check` 只读一次，判定与保存的观察来自同一次读取；产品只给 `error.code` 时，`expectError: {message}` 不成立。
- 会放进审阅状态的每个字段都要能 JSON 序列化；不合规的定义在触碰产品状态之前被拒绝。
- 产品区自己也要能重置产品，不依赖审阅台存在：示例的「重置演示」调用产品自己的重置方法，取消产品自己的定时任务。
