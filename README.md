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
- AI 结果历史、复制及 JSONL 批量导出；结果按数据集保存在浏览器中，刷新页面仍可继续查看
- 并排查看多个模型的 reasoning、final response 和元数据
- 多用户按可配置维度评分、备注、Badcase 与错误标签
- 编辑评分、标签或备注后 1 秒自动暂存；团队模式串行保存并用 revision 防止覆盖冲突
- 导出带标注的完整 JSONL，或只导出扁平标注记录
- 内网团队模式：账号登录、管理员创建/归档/删除项目，创建/停用账号与重置密码
- 项目成员隔离：标注员只看到自己加入的项目和分配给自己的 Case
- 支持按 Case ID 指定或按数量随机分配，可允许多人重叠；也可取消指定任务、清空用户任务或重置项目分配
- 项目级评分维度与 Badcase 标签配置、盲标开关、提交锁定、管理员进度面板和标注退回
- 快速标记“无法判断/数据问题”、上一条/下一条，以及完成整条 Case 后自动前往下一条未完成
- 导入前整文件校验，失败时不修改旧数据；完整 Case / 扁平标注两种导出均可选择是否包含草稿
- 右侧问答支持 Markdown 标题、列表、代码块、表格与安全链接；桌面端打开后压缩主工作区，不再遮挡 Case 内容
- 团队模式支持服务端三阶段 LLM-as-Judge：项目级模型与 Prompt 配置、单条/筛选批量预跑、阶段结果增量展示、共享去重和失败重试
- 自动判分按 Case 内容、候选回复和配置版本分别计算指纹；只修改一个候选时仅该候选结果失效，历史人工标注不受影响
- 自动判分结果可自动加入右侧问答上下文，供标注员继续核查和讨论，不会覆盖人工评分
- 可收起的“标注搭子”：可重命名、换颜色和配饰；摸摸、完成标注及发现 Badcase 会获得经验并升级解锁装扮
- 宠物变身系统：每次升级积攒一次机会；单次消耗 1 次且成功率 10%，合并消耗 5 次必定成功；首次随机进入 5 条形态路线，第二、三次在原路线继续随机强化

宠物经验规则：每次摸摸 `+0.2 EXP`、每小时最多获得 `2 EXP`；首次提交某个候选模型的标注 `+6 EXP`，首次将该结果标为 Badcase 再 `+4 EXP`。同一标注事件不会重复计分；团队模式按账号保存在数据库，本地模式保存在当前浏览器。等级提升后会逐步解锁 8 种颜色、10 种配饰和专属称号。

宠物工作室中的“随机变身实验”会显示可用机会、三阶段形态、已获得特征和最近尝试记录。五条随机路线包含星辉、机甲、森灵、风暴及外观刻意不完美的“歪歪异变体”；路线一旦生成，后续两次成功只强化当前形态。已有账号首次使用时，会按当前等级补发 `等级 - 1` 次机会。

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
- 当前是轻量账号体系：管理员负责创建用户、项目成员和 Case 分配；暂未包含 LDAP/SSO 和密码自助重置。
- 管理员“上传更新”会按稳定的 Case ID 和 candidate ID 原地更新；已有标注、任务分配和未变化内容的判分结果会保留。仍建议更新前备份数据库。

### 团队任务配置流程

1. 管理员创建标注员账号和项目，打开项目后上传 JSONL。
2. 在“项目成员与标注策略”中勾选允许参与该项目的标注员。未加入项目的账号看不到项目。
3. 在“Case 分配与进度”中选择标注员：
   - 输入数量后随机分配；默认不会与其他人的任务重叠。
   - 开启“允许重复”可把同一 Case 分给多人，用于双人盲标或一致性检验。
   - 输入一个或多个 Case ID 可精确指定；也可一键填入管理员当前查看的 Case。
   - “替换已有分配”会先撤销该标注员在项目内的旧任务，再写入本次结果。
4. 默认开启盲标：标注员只能看到自己的评分与备注；管理员可查看全部记录与整体进度。
5. 可选开启“提交后锁定”。管理员在 Case 的标注历史中可将已提交记录退回草稿。

### 三阶段自动判分

1. 管理员打开团队模式和目标项目，在“自动判分配置”中填写服务端可访问的 API Base URL、模型名称与 API Key。
2. 配置 Anthropic `/messages` 或 OpenAI-compatible `/chat/completions` 协议，按需调整三个阶段的温度、最大输出、并发数与阶段三采样次数。
3. 保存会生成新的项目配置版本；点击“测试已保存配置”确认 Case Lens 后端可以访问判分模型。
4. 标注员可在当前 Case 点击“运行自动判分”，也可在团队面板预跑当前筛选或全部可访问 Case。相同内容与配置会自动跳过；排队任务可以取消，已发出的模型请求不会强制中断。
5. “模型结果与标注”页面会先展示 Case 共用的阶段一任务拆解，再在每个候选下展示阶段二检错和阶段三复核评分。结果在项目成员间共享，“判分历史”可查看旧配置或旧候选内容对应的结果。
6. 右侧问答可独立选择是否携带当前 Case、是否加入当前有效的自动判分结果；关闭判分开关不会影响其他 Case 上下文。

判分 API Key 仅保存在后端数据库，不会回传给浏览器。若模型服务使用企业内部 CA，可通过容器系统证书或 `SSL_CERT_FILE` 为 Python 配置信任链；不要关闭 HTTPS 证书校验。

从旧版本升级只需拉取代码并重建：

```bash
docker compose up -d --build
```

启动时会自动创建新的成员与任务分配表，不需要清空 PostgreSQL。已有 Case 和标注不会删除；升级后管理员需要先为旧项目配置成员与 Case 分配，标注员才能继续访问。

### GitLab 导入后脚本没有执行权限

如果构建前端时出现下面的错误：

```text
scripts/build-verified.sh: line 7: /app/scripts/sites-env.sh: Permission denied
```

原因是 `scripts/sites-env.sh` 没有可执行权限。GitLab 导入、压缩包解压或某些文件传输方式可能丢失 Git 的可执行位。先在项目根目录修复并确认权限变化：

```bash
chmod +x scripts/*.sh
git status --short
git diff --summary
```

如果权限此前确实丢失，输出中应出现类似内容：

```text
mode change 100644 => 100755 scripts/sites-env.sh
```

然后重新构建并启动：

```bash
sudo docker compose build --no-cache --progress=plain web
sudo docker compose up -d
```

当前项目的根目录 `Dockerfile` 已在构建时执行 `chmod +x scripts/*.sh`，即使源码传输过程中丢失权限，也会先修复权限再执行前端构建。为了让 GitLab 仓库本身永久保存正确的可执行位，可将权限修复提交到仓库：

```bash
git add Dockerfile
git add --chmod=+x scripts/*.sh
git commit -m "Fix build script permissions and package mirrors"
git push origin main
```

构建完成后检查容器、日志和后端健康状态：

```bash
sudo docker compose up -d
sudo docker compose ps
sudo docker compose logs --tail=100 web api
curl http://127.0.0.1:8080/api/health
```

健康检查正常时返回：

```json
{"status":"ok"}
```

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
    "badcase_tags": ["事实错误", "未遵循指令", "工具调用错误", "推理问题", "其他"],
    "model_order": ["deepseek-v4-flash", "enterprise-9b"]
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
- `annotation_config`：每条 Case 可自定义评分维度；`model_order` 按 `candidate.model`（也兼容 `id` / `label`）配置候选展示顺序，未列出的候选保持 JSONL 原顺序并追加在后。
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

## 连接 NIO Anthropic API

如果本机 `curl` 可以访问 `model.nioint.com`，但网关不允许 Case Lens 的浏览器 Origin，可在打开浏览器的同一台电脑运行仓库内的零依赖中继：

```bash
python3 scripts/model_cors_relay.py \
  --allowed-origin http://10.129.72.139:8080
```

中继只监听 `127.0.0.1:19001`，只接受配置的 Origin，并固定转发 `/v1/messages`。API Key 由当前浏览器请求携带，中继不会保存或输出 Key 和请求正文。启动后可检查：

```bash
curl http://127.0.0.1:19001/health
```

Case Lens 模型配置选择：

- 模式：`外部 API`
- 预设：`NIO 本机中继`
- 协议：`Anthropic · /messages`
- Base URL：`http://127.0.0.1:19001/v1`
- Model：实际模型 ID，例如 `DeepSeek-V4-Flash`
- API Key：仍只保存在当前页面内存

若 Case Lens 的 IP 或端口发生变化，需要用浏览器地址栏中的完整 Origin 重新启动中继。不要使用公开的通用 CORS 代理，也不要把中继绑定到公网地址。

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
