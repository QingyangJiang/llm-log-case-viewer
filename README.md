# LLM Log Case Viewer

一个在浏览器本地查看 LLM JSONL 日志的可视化工具，支持 OpenAI 与 Anthropic 常见消息和工具调用结构。

## 功能

- 拖拽或选择 `.jsonl` / `.json` 文件
- 自动识别 OpenAI、Anthropic 消息协议
- 按 ID、模型、协议和消息内容搜索筛选
- 可视化多轮对话、Thinking、Tool Call 和 Tool Result
- 查看 Tools Schema 与原始 JSON
- 复制或导出单个 Case
- 容错解析：坏行单独提示，不影响其他有效数据
- 日志仅在浏览器本地处理，不上传服务端

## 在线使用

[打开 Case Viewer](https://llm-log-case-viewer.qingyangjiang-aq.chatgpt.site)

## 支持的数据格式

JSONL 每行是一个 JSON object：

```json
{"id":"case-001","messages":[...],"model":"gpt-5.4","tools":[...]}
```

也支持根节点为数组的普通 JSON 文件。

## 本地运行

要求 Node.js `>=22.13.0`。

```bash
npm install
npm run dev
```

生产构建：

```bash
npm run build
```

## 核心代码

- `app/page.tsx`：日志解析、协议识别和交互逻辑
- `app/globals.css`：页面样式与响应式布局
- `app/layout.tsx`：页面元数据与全局布局

## 隐私说明

文件读取和解析均通过浏览器端 File API 完成。项目不包含日志上传接口，也不会把载入的日志保存到服务端。

## License

MIT
