# LLM Log Case Viewer

浏览器本地优先、也可部署为内网多人平台的 JSONL 日志查看与多模型人工标注工具，兼容 OpenAI 与 Anthropic 常见消息结构。

## 主要功能

- 拖拽或选择 `.jsonl` / `.json`，坏行单独提示，不影响其他 Case
- 自动识别 OpenAI、Anthropic 消息、Thinking、Tool Call 与 Tool Result
- 按 ID、模型、协议、消息内容搜索和筛选
- 查看对话轨迹、Tools Schema、原始 JSON，复制或导出 Case
- 大列表分批渲染，大型 JSONL 让出主线程分批解析
- `⌘/Ctrl + K` 聚焦搜索，方向键切换 Case
- 使用本地模型或外部 OpenAI-compatible API 翻译、摘要、双语摘要和自定义分析
- 支持当前 Case、单条消息或当前筛选结果批量处理
- 执行前估算 Token、分片和请求次数；按模型上下文窗口自动计算安全输入预算
- 翻译逐段完整处理并按原顺序拼接；摘要采用分段提炼 + 多层合并，不静默抽样
- AI 结果历史、复制及 JSONL 批量导出
- 并排查看多个模型的 reasoning、final response 和元数据
- 多用户按可配置维度评分、备注、Badcase 与错误标签
- 草稿自动暂存在浏览器；支持提交状态、左侧状态筛选和多人标注历史
- 导出带标注的完整 JSONL，或只导出扁平标注记录
- 内网团队模式：账号登录、管理员创建项目/用户、统一草稿与提交、项目进度和管理员导出

## 在线使用

[打开 Case Viewer](https://llm-log-case-viewer.qingyangjiang-aq.chatgpt.site)

日志文件在浏览器内读取和解析，不上传到本站服务端。仅当你主动执行 AI 任务时，选中的文本才会发送到配置的模型地址。

在线地址是前端功能演示，不连接你的内网数据库。正式多人标注请按下文使用 Docker Compose 部署。

## 内网一键部署

不需要域名。只要标注用户能访问服务器内网 IP，即可通过 `http://<服务器内网IP>:8080` 使用。

要求：Linux x86_64/ARM64 服务器、Docker Engine 24+、Docker Compose v2；建议至少 4 核 CPU、8 GB 内存，并为数据预留足够磁盘。

```bash
git clone https://github.com/QingyangJiang/llm-log-case-viewer.git
cd llm-log-case-viewer
cp .env.example .env
```

先编辑 `.env`，至少替换 `POSTGRES_PASSWORD` 和 `ADMIN_PASSWORD`。然后执行：

```bash
bash scripts/preflight-deploy.sh
docker compose up -d --build
docker compose ps
curl http://127.0.0.1:8080/api/health
```

健康检查返回 `{"status":"ok"}` 后，在其他内网机器打开 `http://<服务器内网IP>:8080`。点击右上角“团队模式”，用 `.env` 中的管理员账号登录；创建项目、打开项目、上传 JSONL，再创建标注员账号。

部署包含四个容器：Nginx（唯一暴露端口）、前端、FastAPI、PostgreSQL。PostgreSQL 不对外开放；数据库、上传文件和导出数据分别持久化在 `./data/postgres` 与 `./data/app`。重启容器不会丢失。

常用运维命令：

```bash
# 查看状态和日志
docker compose ps
docker compose logs -f --tail=200

# 更新代码并滚动重建
git pull --ff-only
docker compose up -d --build

# 停止服务（保留数据）
docker compose down

# PostgreSQL 逻辑备份
docker compose exec -T postgres pg_dump -U case_lens case_lens > data/case-lens-backup.sql
```

注意事项：

- 不要执行 `docker compose down -v`，也不要删除 `data/`，除非确认要清空全部数据。
- 若修改了 `POSTGRES_USER` / `POSTGRES_DB`，备份命令中的名称也要同步修改。
- HTTP 内网部署请保持 `SECURE_COOKIES=false`；未来接入 HTTPS 后改为 `true`。
- 防火墙只需向可信内网开放 `APP_PORT`。可修改 `.env` 中的 `APP_PORT`，例如 `8090`。
- 当前是轻量账号体系：管理员可创建用户和项目，所有已登录用户均可看到全部项目；暂未包含项目级权限分配、LDAP/SSO 和密码自助重置。
- 管理员“上传并替换”会清除该项目原有 Cases 及其标注；操作前先导出或备份。

## 数据格式

旧格式仍可直接查看：

```json
{"id":"case-001","messages":[...],"model":"gpt-5.4","tools":[...]}
```

也支持根节点为数组的普通 JSON 文件。

用于多模型标注时，推荐使用 `case-lens.annotation.v1`。JSONL 每行是一条独立 Case：

```json
{
  "schema_version": "case-lens.annotation.v1",
  "id": "case-001",
  "messages": [
    {"role": "system", "content": "You are a helpful assistant."},
    {"role": "user", "content": "用户问题"}
  ],
  "tools": [],
  "candidates": [
    {
      "id": "model-a",
      "model": "enterprise-9b",
      "label": "9B 企业模型",
      "reasoning": "模型思考过程；也可以是协议内容块数组",
      "response": "模型最终回复；也可以是协议内容块数组",
      "metadata": {"latency_ms": 1200, "tokens": 850}
    },
    {
      "id": "model-b",
      "model": "deepseek-v4-flash",
      "label": "线上中杯",
      "reasoning": "另一个模型的思考过程",
      "response": "另一个模型的最终回复"
    }
  ],
  "annotation_config": {
    "dimensions": [
      {"key": "correctness", "label": "正确性", "description": "事实与结论是否正确", "min": 1, "max": 5, "required": true},
      {"key": "relevance", "label": "相关性", "min": 1, "max": 5, "required": true}
    ],
    "badcase_tags": ["事实错误", "未遵循指令", "工具调用错误", "推理问题", "其他"]
  },
  "annotations": [
    {
      "annotation_id": "case-001:model-a:jiangqy",
      "annotator": {"id": "jiangqy", "name": "姜庆阳"},
      "candidate_id": "model-a",
      "scores": {"correctness": 4, "relevance": 5},
      "badcase": false,
      "badcase_tags": [],
      "note": "结论正确，但引用不够具体",
      "status": "submitted",
      "created_at": "2026-08-12T08:00:00.000Z",
      "updated_at": "2026-08-12T08:05:00.000Z"
    }
  ]
}
```

字段约定：

- `messages` / `tools`：所有候选模型共享的输入上下文，继续兼容原格式。
- `candidates`：同一 Case 的多个待评模型结果；`id` 在 Case 内唯一且稳定。
- `reasoning` / `response`：支持字符串、JSON object 或 OpenAI/Anthropic 内容块数组。
- `annotation_config`：每条 Case 可自定义评分维度；缺省时使用正确性、相关性、完整性、表达质量四个 1–5 分维度。
- `annotations`：可同时保存多名用户对不同候选模型的记录；唯一逻辑键为 `case id + candidate_id + annotator.id`。
- `status`：`draft` 表示暂存，`submitted` 表示完成。提交时会校验所有必填维度。

页面左侧可按未标注、草稿、已完成和 Badcase 筛选。本地模式的草稿保存在浏览器 `localStorage`；团队模式的草稿和提交均保存到 PostgreSQL，并带 revision 防止旧页面覆盖新版本。页面中的“下载输入模板”可直接获取一行示例。

## 本地运行

要求 Node.js `>=22.13.0`：

```bash
npm install
npm run dev
```

生产构建与检查：

```bash
npm run lint
npm test
```

## 连接本地模型

工具调用 OpenAI-compatible `/chat/completions` 接口。

Ollama 默认配置：

- Base URL：`http://localhost:11434/v1`
- Model：例如 `qwen3:8b`

若浏览器提示 CORS，可在可信本机环境中允许网页来源后启动 Ollama：

```bash
OLLAMA_ORIGINS=* ollama serve
```

vLLM / SGLang 常用 Base URL 为 `http://localhost:8000/v1`。线上 HTTPS 页面访问本地 HTTP 服务可能被浏览器拦截；遇到这种情况，推荐在本机运行 Viewer，或为模型服务配置 HTTPS / 可信代理。

## 大文件与上下文窗口

在 AI 面板的“上下文与输出”配置区填写模型真实支持的上下文窗口和输出 Token。两项均支持任意数值输入，上下文同时提供 4K–256K 快捷值。工具会扣除系统提示和安全余量，实时计算单段输入预算：

- 翻译：根据“单次最大输出”反推安全片段大小，为译文保留约输入 1.5 倍空间；所有片段依次调用并按原顺序拼接
- 摘要：先生成每个片段的摘要，再按上下文预算进行多层 Map-Reduce 合并
- 双语摘要：最后一层才生成中英双语结果，避免中间结果过长
- 自定义任务：仍是单次调用；超长时会明确标记首尾截断
- 如果完整处理需要的片段数超过安全上限，任务会被阻止并提示调整，不会通过抽样悄悄遗漏日志

Token 数是浏览器端对中英文混合文本的近似估算。建议上下文窗口填写真实值，并保留至少 1K–2K 输出空间；本地小模型可先从 8K 上下文、1K 输出预留开始。

## 隐私说明

- 日志加载、搜索、筛选和导出均在浏览器本地完成
- API Key 只保存在当前页面内存，不写入 localStorage
- 模型地址、模型名和长文本配置可以保存在当前设备
- 外部 API 模式会把本次选中的日志文本直接发送给配置的服务商
- 可在高级设置中排除 System / Developer、Thinking 或 Tools 定义

## License

MIT
