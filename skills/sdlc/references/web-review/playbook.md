# web-review：可选的浏览器划词复核

web-review 是产品或研发 Markdown 的可选复核界面。它只改善用户反馈方式，不维护生命周期状态，也不在仓库生成报告。

## 何时使用

- 文档较长、表格多或跨多个章节，聊天逐条反馈效率低。
- 用户明确要求网页查看、划词批注或浏览器复核。
- 简短文档默认直接在对话中复核。

## 来源文件

由当前阶段明确指定一个 Git 跟踪的 Markdown：

- 产品问题、场景、规则和验收条件：`.sdlc-v1/context/<REQ>.product.md`。
- 技术设计、Task、测试策略和实施决策：`.sdlc-v1/context/<FEAT>.engineering.md`。
- 项目技术入口和约定：`.sdlc-v1/project.md`。

不要默认读取旧 SDLC 路径，也不要复制来源文档形成第二份正文。

## 工具资产

| 文件 | 职责 |
|---|---|
| `build.py` | 将 Markdown 渲染为可批注页面 |
| `annotate.js` / `annotate.css` | 选中文字、评论、定位和提交 |
| `server.py` | 仅在 localhost 托管页面并回收反馈 |

工具产物放临时目录，例如 `<tmp-root>/sdlc-web-review-<slug>/`，不提交到目标仓库。

## 流程

1. **确定来源**：记录唯一来源 Markdown 的绝对路径。
2. **生成页面**：运行 `build.py <source.md> <outdir> --title "<title>"`。
3. **本地打开**：在临时目录启动 `server.py`，只绑定 `127.0.0.1`。
4. **用户批注**：用户选中文字、写评论并选择 `approve` 或 `changes`。
5. **回收反馈**：读取临时目录的 `feedback.json`。
6. **统一修改**：按 `section + quote` 在唯一来源 Markdown 中精确定位，集中应用已理解的修改。
7. **处理歧义**：quote 找不到或 comment 有多种解释时，向用户澄清，不猜测。
8. **回复批注**：可将每条处理结果写到临时目录 `replies.json`，供页面展示。
9. **再次复核**：有修改时按需重新渲染；批准后由拥有该文档的阶段技能继续正常流程。
10. **收尾**：停止本地服务器；临时产物可清理，不写入 Git。

`feedback.json` 示例：

~~~json
{
  "verdict": "changes",
  "annotations": [
    {
      "id": "a1",
      "section": "Acceptance",
      "quote": "existing text",
      "comment": "add the missing boundary case"
    }
  ]
}
~~~

## 批准语义

- `approve`：用户批准当前来源文档。
- `changes`：应用意见后重新复核。
- web-review 自身不编辑 `state.json`，不写 status、next 或其他进度字段。
- 产品、研发、验证、评审或发布阶段仍由各自阶段技能决定何时调用 lifecycle state 命令。
- 批准记录和重要决策直接写回唯一来源 Markdown 的相关章节。

## Live mode

需要实时回收时，可以在服务器运行期间前台等待 `GET /wait`：

1. 页面提交反馈后，`POST /feedback` 唤醒等待请求。
2. agent 收到反馈，修改来源 Markdown。
3. 页面按 revision 变化刷新，再次等待。
4. 超时后重新等待；无浏览器或无 curl 时退回文件式回收或对话复核。

`server.py` 必须使用可并发处理请求的服务器，避免等待请求阻塞反馈提交。等待期间只保留浏览器这一条交互渠道；需要澄清时先结束等待，再回到对话。

## 约束

- 只绑定 localhost，不出网。
- 临时 `feedback.json` 和 `replies.json` 不是项目事实来源。
- 来源 Markdown 始终只有一份。
- 批注匹配失败时不臆改。
- 无浏览器时直接使用对话复核，不创建替代进度文件。
