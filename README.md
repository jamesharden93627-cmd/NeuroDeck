# NeuroDeck

NeuroDeck 是一个本地优先的 AI Observability & Command Center。当前纵向切片已经可以把 Codex、Antigravity、Ollama 和本机硬件状态统一展示在一个 React NOC 主屏中。

## 当前能力

- React 19 + Vite + TypeScript 的响应式 Command Center
- FastAPI REST 首帧与 WebSocket 实时推送
- SQLite 本地历史持久化，服务重启后趋势与最近信号不会丢失
- 今日 / 7D / 30D 本地自然日范围查询，按 5 分钟 / 30 分钟 / 2 小时自动聚合
- 只读解析 Codex `sessions/**/*.jsonl` 中的 token 元数据
- 读取 Codex 当前模型、上下文，并按本地日期跨 session 汇总输入/输出/缓存/推理 token
- 被动读取 Ollama `/api/ps` 与 `/api/show`，不改变现有 Ollama 使用方式
- 独立 Ollama 流式代理端口 `11435`，精确记录输入/输出 token、tokens/s、请求数与耗时
- 使用 `psutil` 采集 CPU、频率、RAM 和系统 uptime
- NVIDIA：通过 `nvidia-smi` 采集利用率、显存、温度、功耗与风扇
- Windows AMD/Intel：通过系统性能计数器采集 GPU 利用率和专用显存
- API 未启动时显示等待采集提示并自动重连，首帧之前不展示演示统计
- Overview、Ollama、Codex、Hardware 四个可切换实时视图

## 本地启动

首次安装：

```powershell
python -m venv .venv
.\.venv\Scripts\python.exe -m pip install -r backend\requirements.txt
Set-Location frontend
npm install
npm run build
Set-Location ..
```

只启动 FastAPI 即可同时访问 production React 页面，并自动监听 Ollama 代理端口 `11435`：

```powershell
Set-Location backend
..\.venv\Scripts\python.exe -m uvicorn app.main:app --host 127.0.0.1 --port 5188
```

打开 [http://127.0.0.1:5188](http://127.0.0.1:5188)。

Windows 下也可以直接双击 `start-neurodeck.cmd`：服务会隐藏运行、健康检查通过后
自动打开浏览器，日志写入 `data/logs/`。双击 `stop-neurodeck.cmd` 可安全停止由该
脚本启动的进程。

历史数据库默认保存在 `data/neurodeck.db`，只记录 token 数值、硬件指标和状态事件，
不保存 prompt、response 或工具输出。默认保留 30 天，可通过环境变量调整：

```powershell
$env:NEURODECK_DATABASE_PATH = "D:\NeuroDeckData\neurodeck.db"
$env:NEURODECK_HISTORY_RETENTION_DAYS = "30"
$env:NEURODECK_HISTORY_SAMPLE_INTERVAL = "10"
```

页面默认每秒刷新；SQLite 趋势默认每 10 秒落盘一次，状态事件仍会立即保存。

Codex 日统计使用每次 `token_count.last_token_usage` 事件按系统本地日期累加，避免把
最新 rollout 的累计值误当成当天总量。扫描范围包含 sessions 与 archived_sessions；
相同事件和用量累计未变化的重复通知不会重复累加。首次启动从本地 JSONL 重建，
后续只扫描追加部分。原始 JSONL 未被修改，删除所有源日志后独立恢复账本仍属后续工作。

`GET /api/codex/accounting` 可查看最近 30 个自然日的原始/去重后数值与重复事件数。
这是本地元数据对账，并非账户账单接口；修改前保存的趋势快照保留原样，不自动回写。

历史聚合接口：

```text
GET /api/analytics/history?range=24H
GET /api/analytics/history?range=7D
GET /api/analytics/history?range=30D
```

兼容 API 继续使用 `24H` 作为今日的标识，界面已改为“今日 / Today”。KPI、历史查询
与图表起点均使用服务器的本地自然日；7D/30D 包含今天。曲线仍为每日累计快照，
不是每个时间桶的消耗增量，午夜归零是该曲线的统计含义。

## Ollama 精确统计

Ollama 的 `/api/ps` 只能显示当前驻留模型，无法看到其他客户端请求的 token 和生成速度。
需要精确统计的客户端请把 Ollama Base URL 从 `http://127.0.0.1:11434` 改为：

```text
http://127.0.0.1:11435
```

NeuroDeck 会把请求原样转发到真实 Ollama：

```text
调用方 → http://127.0.0.1:11435 → http://127.0.0.1:11434
```

PowerShell 中可仅对当前终端启用代理：

```powershell
$env:OLLAMA_HOST = "http://127.0.0.1:11435"
ollama run qwen3.8-IQ4:latest
```

流式生成期间，页面会每秒显示带 `~` 的 output token 与 tokens/s 估算；
Ollama 最终响应块到达后，会自动替换为官方 `eval_count` 和 `eval_duration` 精确值。
输入 token 只有请求完成后才由 Ollama 返回，因此生成中继续显示已完成请求的精确累计值。
当前 tokens/s 在请求结束后归零，最近一次精确速度仅保留在完成事件和详情说明中。
上下文上限优先读取 `/api/ps.context_length` 的已加载运行时配置，而不是模型文件容量。

例如发送到 `11435` 的原请求 `POST /api/chat` 会通过 NeuroDeck 转发到 `11434`，流式响应保持原样。
代理只保存模型、输入/输出 token、耗时和 tokens/s，不保存 prompt、response、thinking
或工具调用正文。未经过该地址、仍直接访问 `11434` 的请求只能监控模型驻留和硬件状态。

代理支持原生 NDJSON、非流式 JSON 和 OpenAI 兼容 SSE 的 usage 统计；上游未返回 usage
时标记 unmetered/incomplete，不伪造精确 token 或生成速度。失败、取消会保存匿名状态和
错误类型（不保存错误正文）。`GET /api/ollama/requests?limit=50` 提供最近请求结果。
首次从旧库升级会生成 `data/neurodeck.pre-v2.db` 备份，只增添状态字段，不删除原记录。

`GET /api/health` 分别报告 API、采集新鲜度与存储状态。
`GET /api/codex/accounting?range=7D` 返回所选自然日范围的原始、接受和重复 Token；
Codex 详情页会校验 `原始量 = 展示量 + 过滤量`，并与同一帧的页面合计对账。
前端断线会显示旧快照提示，重连重新补拉历史，历史加载失败时隐藏旧范围并自动重试。

趋势图按所选 24H / 7D / 30D 的真实时间轴定位，并分别缩放 Ollama 与 Codex 曲线，
避免两者相差数千倍时 Ollama 被压成零线。页面会显示实际数据覆盖率；只有最近两三天
数据时，7D/30D 左侧会保留空白，不再把少量数据拉伸成完整周期。

React 开发模式使用两个终端：

```powershell
# Terminal 1
Set-Location backend
..\.venv\Scripts\python.exe -m uvicorn app.main:app --host 127.0.0.1 --port 5188 --reload

# Terminal 2
Set-Location frontend
npm run dev
```

开发页面位于 [http://127.0.0.1:5173](http://127.0.0.1:5173)。

## 验证

```powershell
python -m pytest -q
Set-Location frontend
npm run lint
npm test
npm run build
```

## 隐私边界

- 默认只监听 `127.0.0.1`。
- Codex Collector 只提取事件类型、模型和 token 数值字段。
- 不保存 prompt、response、工具输出或对话正文。
- Ollama 第一版为被动监控；没有经过代理的请求不会伪造 token/s。
- GPU 温度或功耗无法从当前驱动可靠获取时，UI 显示 `—`。

## 下一步

1. Codex 独立持久化账本、模型与工作区使用排行。
2. 代理端到端延迟、首 Token 时间与告警规则。
3. AMD 温度/功耗 Provider 与 Collector 插件注册机制。

## 请求分析

侧栏“请求分析 / Requests”提供 Ollama 请求运营视图：

- 今日、7D、30D 共享本地自然日边界；模型、状态、请求 ID 筛选联动卡片、趋势、排行和列表。
- 请求量、成功率、精确 Token、平均与 P95 推理耗时，前十模型用量排行、每日输入/输出增量柱图。
- 请求详情包含匿名 ID、接口、HTTP 状态、计量精度与错误类型；支持每页 10/20/50 条和当前页 CSV 导出。
- 首页每 5 秒更新；后续页固定记录水位，刷新返回最新首页。数据获取失败会提示并自动重试。

接口：`GET /api/analytics/operations?range=7D&model=&status=&search=&page=1&page_size=20`。
响应含 `snapshot_id`，翻页时带回可防止新增请求导致重复或漏行。
同一接口添加 `format=csv` 返回当前筛选页的 CSV 附件，含 UTF-8 BOM 与公式前缀转义。

统计口径：成功率 = completed + unmetered / 全部已结束请求；失败、取消、未完成仍在分母中。
Token 仅统计 completed 且 exact 的输入与输出。耗时仅使用已完成请求中 Ollama 上报的正值，
P95 使用最近秩法；这是模型服务上报的总推理耗时，不是代理端到端延迟或首 Token 时间。
没有样本的成功率、耗时和速度显示 `—`，不冒充 0。尚未有请求级 Codex 成功率和延迟统计。
总览在初次连接或连接失败时不再自动显示演示数据；采集到真实首帧后才显示指标。
