# NeuroDeck 建设清单与建设思路

> **项目定位**  
> NeuroDeck 是一个面向本地 AI 工作流的轻量级 Observability & Command Center。  
> 第一阶段重点监控 **Ollama + Codex + 本机硬件**，统一展示模型、Token、吞吐率、上下文、会话、GPU/VRAM、CPU/RAM、温度等信息。  
> 后续可扩展到 Claude Code、OpenCode、Gemini CLI、Agent、RAG、Tool Calling、AI Video 等。

---

## 1. 建设目标

### 1.1 第一阶段目标：做成“每天能用”的本地监控工具

启动 NeuroDeck 后：

1. 后台自动采集 Codex 使用情况。
2. 自动采集 Ollama 当前运行模型、Token 和推理性能。
3. 自动采集 CPU、内存、GPU、显存、温度等硬件指标。
4. 浏览器访问本地 Dashboard 即可查看所有数据。
5. 所有监控数据默认只保存在本机。
6. 用户正常使用 Codex、Ollama，不要求改变原有工作习惯。

目标体验：

```text
启动 NeuroDeck
      ↓
后台 Collector 自动运行
      ↓
http://localhost:5188
      ↓
AI COMMAND CENTER

LOCAL AI
Qwen3.8-27B
23.4 tok/s
Context 32K
Today 328K Tokens

CODEX
GPT-5.x
Today 1.82M Tokens
Sessions 14

SYSTEM
GPU 96%
VRAM 14.2 / 16 GB
GPU Temp 67°C
CPU 24%
RAM 36 / 64 GB
```

---

## 2. 技术路线

### 2.1 推荐技术栈

**Backend**

- Python 3.12+
- FastAPI
- Uvicorn
- asyncio
- httpx
- psutil
- watchdog
- SQLite
- SQLModel 或 SQLAlchemy
- Pydantic
- WebSocket

**Frontend**

- Vue 3
- Vite
- TypeScript
- Pinia
- Vue Router
- ECharts
- Tailwind CSS 或自定义 CSS Variables

**桌面 / 分发**

第一阶段：

```text
Python Backend
+
Vue build static files
+
浏览器访问 localhost
```

后续：

```text
PyInstaller
→ NeuroDeck.exe
```

再后续可选：

```text
Tauri
```

用于制作真正的桌面壳。

---

## 3. 总体架构

```text
                         NeuroDeck
                            │
          ┌─────────────────┼───────────────────┐
          │                 │                   │
          ▼                 ▼                   ▼
    Codex Collector   Ollama Collector    Hardware Collector
          │                 │                   │
          │                 │                   │
   JSONL / Sessions     Ollama API         OS / GPU Metrics
          │                 │                   │
          └────────────┬────┴────────────┬──────┘
                       │                 │
                       ▼                 ▼
                  Normalize         Real-time State
                       │
                       ▼
                     SQLite
                       │
                       ▼
                    FastAPI
                       │
             ┌─────────┴─────────┐
             │                   │
             ▼                   ▼
           REST API           WebSocket
             │                   │
             └─────────┬─────────┘
                       ▼
                  Vue Dashboard
```

核心原则：

> **Collector 只负责采集。  
> Service 负责业务计算。  
> Database 负责历史数据。  
> API 负责输出。  
> Vue 负责展示。**

不要让某一个 Collector 同时负责采集、统计、数据库和 UI。

---

## 4. 推荐项目结构

```text
neurodeck/
│
├── backend/
│   ├── app/
│   │   ├── main.py
│   │   │
│   │   ├── api/
│   │   │   ├── dashboard.py
│   │   │   ├── ollama.py
│   │   │   ├── codex.py
│   │   │   ├── hardware.py
│   │   │   └── sessions.py
│   │   │
│   │   ├── collectors/
│   │   │   ├── base.py
│   │   │   ├── ollama_collector.py
│   │   │   ├── codex_collector.py
│   │   │   └── hardware_collector.py
│   │   │
│   │   ├── services/
│   │   │   ├── dashboard_service.py
│   │   │   ├── token_service.py
│   │   │   ├── session_service.py
│   │   │   └── metrics_service.py
│   │   │
│   │   ├── models/
│   │   │   ├── database.py
│   │   │   ├── usage.py
│   │   │   ├── session.py
│   │   │   └── hardware.py
│   │   │
│   │   ├── schemas/
│   │   │   ├── ollama.py
│   │   │   ├── codex.py
│   │   │   └── dashboard.py
│   │   │
│   │   ├── db/
│   │   │   ├── engine.py
│   │   │   ├── repository.py
│   │   │   └── migrations/
│   │   │
│   │   ├── core/
│   │   │   ├── config.py
│   │   │   ├── logging.py
│   │   │   └── constants.py
│   │   │
│   │   └── websocket/
│   │       └── manager.py
│   │
│   ├── tests/
│   ├── requirements.txt
│   └── pyproject.toml
│
├── frontend/
│   ├── src/
│   │   ├── api/
│   │   ├── components/
│   │   ├── views/
│   │   ├── stores/
│   │   ├── router/
│   │   ├── charts/
│   │   ├── types/
│   │   └── styles/
│   ├── package.json
│   └── vite.config.ts
│
├── docs/
│   ├── architecture.md
│   ├── ollama.md
│   ├── codex.md
│   └── database.md
│
├── data/
│   └── neurodeck.db
│
├── scripts/
│
├── README.md
├── LICENSE
└── .gitignore
```

---

## 5. 数据采集设计

### 5.1 Ollama Collector

第一版采集：

- 当前运行模型
- 模型名称
- 模型大小
- context
- processor CPU/GPU 比例
- prompt token
- output token
- prompt eval duration
- eval duration
- prompt tokens/s
- generation tokens/s
- total duration
- load duration
- 请求时间
- 请求状态

Ollama 常用数据源：

```text
/api/ps
/api/tags
/api/generate
/api/chat
```

第一阶段可分两步：

**阶段 A：Passive Monitor**

只调用：

```text
/api/ps
/api/tags
```

用于监控当前状态。

优点：

- 简单
- 不改变 Ollama 使用方式
- 风险低

缺点：

- 不能可靠捕获所有历史请求 Token

**阶段 B：Ollama Proxy**

增加：

```text
Client
   ↓
NeuroDeck Proxy :11435
   ↓
Ollama :11434
```

Proxy 可以精确记录：

```text
prompt_eval_count
eval_count
prompt_eval_duration
eval_duration
total_duration
```

后续所有需要精确 Token 历史的应用，可将 Ollama Base URL 设置为：

```text
http://localhost:11435
```

---

## 6. Codex Collector

第一版目标：

> 用户正常打开 Codex Desktop / Codex CLI，NeuroDeck 自动读取本地使用数据。

监控方式：

```text
Codex
   ↓
Local Session / JSONL
   ↓
FileSystemWatcher
   ↓
Codex Collector
```

重点采集：

- session id
- workspace
- model
- timestamp
- input tokens
- output tokens
- cached input tokens
- reasoning tokens（如果数据中存在）
- total tokens
- request count
- conversation duration
- tool call 数量
- error 数量

实现重点：

1. 第一次启动扫描已有 session。
2. 记录每个文件最后处理 offset。
3. 后续只读取新增内容。
4. 防止重复统计。
5. 文件异常时不能让整个 Collector 崩溃。
6. Codex 格式变化时记录 warning，而不是直接失败。

建议维护一个 parser version：

```text
CodexParserV1
CodexParserV2
```

避免以后 Codex 日志格式变化导致整体重写。

---

## 7. Hardware Collector

第一版：

- CPU utilization
- CPU frequency
- RAM used
- RAM total
- process memory
- GPU utilization
- VRAM used
- VRAM total
- GPU temperature

第二版：

- GPU hotspot
- GPU power
- fan RPM
- CPU temperature
- disk usage
- network usage
- per-process GPU usage

Python 优先：

```text
psutil
```

GPU 信息可抽象：

```python
class GpuProvider:
    async def get_metrics(self) -> GpuMetrics:
        ...
```

具体实现：

```text
AMD Provider
NVIDIA Provider
Fallback Provider
```

不要在 HardwareCollector 中写死 AMD。

---

## 8. 数据模型

### usage_events

```text
id
provider
model
session_id
timestamp

prompt_tokens
completion_tokens
cached_tokens
total_tokens

prompt_eval_duration
eval_duration
total_duration

prompt_tokens_per_second
tokens_per_second

context_size
status
```

provider：

```text
ollama
codex
claude
gemini
opencode
```

### sessions

```text
id
provider
external_session_id
model
workspace

started_at
ended_at

prompt_tokens
completion_tokens
cached_tokens
total_tokens

request_count
tool_call_count
error_count
```

### hardware_metrics

```text
id
timestamp

cpu_usage
cpu_frequency

ram_used
ram_total

gpu_name
gpu_usage

vram_used
vram_total

gpu_temperature
gpu_hotspot
gpu_power
fan_rpm
```

### models

```text
id
provider
model_name
display_name
model_size
quantization
context_size
first_seen
last_seen
```

---

## 9. API 设计

第一版 REST API：

```text
GET /api/dashboard/overview

GET /api/ollama/status
GET /api/ollama/usage
GET /api/ollama/models

GET /api/codex/status
GET /api/codex/usage
GET /api/codex/sessions

GET /api/hardware/current
GET /api/hardware/history

GET /api/analytics/tokens
GET /api/analytics/throughput
GET /api/analytics/models
```

实时：

```text
WS /ws/realtime
```

WebSocket 推送：

```json
{
  "type": "hardware",
  "data": {}
}
```

```json
{
  "type": "ollama",
  "data": {}
}
```

```json
{
  "type": "codex",
  "data": {}
}
```

---

## 10. Dashboard 页面设计

### Overview

整个 NeuroDeck 最重要的一页。

顶部：

```text
NEURODECK
AI OBSERVABILITY COMMAND CENTER

SYSTEM ONLINE
LOCAL AI ONLINE
CODEX CONNECTED
```

核心卡片：

```text
LOCAL AI
Qwen3.8-27B
23.4 tok/s
32K Context

CODEX
GPT-5.x
1.82M tokens today

GPU
RX 7800 XT
96%
14.2 / 16 GB
67°C

SYSTEM
CPU 24%
RAM 36 / 64 GB
```

图表：

```text
Token Throughput
Token Usage Timeline
GPU Usage
VRAM Usage
Temperature
Provider Distribution
Model Distribution
```

最近活动：

```text
20:31 Ollama Qwen3.8   1,842 tokens
20:27 Codex GPT-5.x   28,341 tokens
20:20 Ollama Gemma4     942 tokens
```

---

## 11. Ollama 页面

展示：

```text
Active Model
Quantization
Context
Processor CPU/GPU
Model Size
Tokens/s
Prompt Tokens/s
Current Session
Today Tokens
Total Requests
Average Latency
```

趋势图：

```text
Generation Speed
Prompt Speed
Context Usage
Request Duration
Token Usage
```

模型排行：

```text
Qwen3.8
Gemma4
Qwen3.5
...
```

---

## 12. Codex 页面

显示：

```text
Current Model
Today Tokens
Input Tokens
Output Tokens
Cached Tokens
Sessions
Tool Calls
Average Session Size
```

Workspace：

```text
Project A
Project B
Project C
```

按项目统计：

```text
Tokens
Sessions
Models
Duration
```

---

## 13. Hardware 页面

大号 GPU 卡：

```text
AMD Radeon RX 7800 XT

GPU        96%
VRAM       14.2 / 16 GB
TEMP       67°C
HOTSPOT    82°C
POWER      238W
FAN        1850 RPM
```

CPU：

```text
Ryzen 9 9950X

CPU        21%
CLOCK      xxxx MHz
RAM        36 / 64 GB
```

实时曲线：

```text
GPU Usage
VRAM
Temperature
CPU
RAM
```

---

## 14. UI 风格

关键词：

```text
Dark
Cyber
NOC
HUD
Command Center
AI Lab
Minimal Neon
```

颜色不要太花。

建议基础：

```text
Background     #060B14
Panel          #0C1422
Border         rgba(...)
Text Primary   #EAF2FF
Text Secondary #7F91A8
```

只使用 1～2 个主 accent。

设计重点：

- 深色背景
- 微弱网格
- 轻量发光
- 数据字体使用等宽字体
- 大数字
- 小面积 neon
- 状态灯
- 动态曲线
- 不要做廉价“赛博朋克”

---

## 15. 开发阶段规划

### Phase 0 — 验证数据源

- [ ] 建立 Git Repository
- [ ] Python 环境
- [ ] FastAPI Hello World
- [ ] 调用 Ollama `/api/ps`
- [ ] 成功读取 Codex session
- [ ] 用 psutil 获取 CPU/RAM
- [ ] 获取 AMD GPU / VRAM / 温度
- [ ] 将以上数据打印成统一 JSON

**完成标准**

```text
python main.py

可以打印：

Ollama
Codex
CPU
RAM
GPU
VRAM
Temperature
```

---

### Phase 1 — Collector

- [ ] BaseCollector
- [ ] OllamaCollector
- [ ] CodexCollector
- [ ] HardwareCollector
- [ ] asyncio 后台运行
- [ ] Collector 生命周期管理
- [ ] Exception isolation
- [ ] logging
- [ ] graceful shutdown

完成标准：

> 三个 Collector 可以同时长期运行，不互相影响。

---

### Phase 2 — SQLite

- [ ] SQLModel / SQLAlchemy
- [ ] 创建 usage_events
- [ ] 创建 sessions
- [ ] 创建 hardware_metrics
- [ ] Repository Pattern
- [ ] 避免重复 Codex Event
- [ ] 数据保留策略
- [ ] Index

完成标准：

> 关闭 NeuroDeck 再启动，历史统计不会丢失。

---

### Phase 3 — REST API

- [ ] `/api/dashboard/overview`
- [ ] `/api/ollama/status`
- [ ] `/api/ollama/usage`
- [ ] `/api/codex/usage`
- [ ] `/api/codex/sessions`
- [ ] `/api/hardware/current`
- [ ] `/api/hardware/history`
- [ ] OpenAPI 文档

---

### Phase 4 — Vue Dashboard

- [ ] Vue3
- [ ] TypeScript
- [ ] Pinia
- [ ] Router
- [ ] API client
- [ ] Layout
- [ ] Overview
- [ ] Ollama
- [ ] Codex
- [ ] Hardware
- [ ] Responsive

第一版先保证：

> 数据准确 > 页面炫酷。

---

### Phase 5 — Realtime

- [ ] FastAPI WebSocket
- [ ] WebSocket manager
- [ ] Hardware 1～2 秒刷新
- [ ] Ollama 状态实时刷新
- [ ] Codex 新事件推送
- [ ] 前端自动 reconnect
- [ ] 防止浏览器关闭导致服务异常

---

### Phase 6 — UI Upgrade

- [ ] ECharts
- [ ] Token 实时折线
- [ ] GPU 曲线
- [ ] VRAM 曲线
- [ ] Temperature
- [ ] Animated counters
- [ ] Status lights
- [ ] Command Center layout
- [ ] Dark theme
- [ ] Loading skeleton
- [ ] Empty state

---

### Phase 7 — Ollama Proxy

- [ ] `/api/chat` proxy
- [ ] `/api/generate` proxy
- [ ] Streaming passthrough
- [ ] Token metrics capture
- [ ] Duration capture
- [ ] Abort handling
- [ ] Error capture
- [ ] Request ID
- [ ] Session correlation
- [ ] 不保存 prompt 默认内容

目标：

> NeuroDeck 可以准确统计所有经过 Proxy 的 Ollama 请求。

---

### Phase 8 — 安全与隐私

默认原则：

```text
Local First
No Cloud
No Prompt Storage
No Response Storage
```

- [ ] 只监听 localhost
- [ ] 不默认开放局域网
- [ ] 不保存 Prompt
- [ ] 不保存 Response
- [ ] 日志过滤敏感数据
- [ ] DB 仅保存在本机
- [ ] API CORS 限制
- [ ] Path validation
- [ ] Codex 文件只读
- [ ] Proxy 不修改请求内容

---

### Phase 9 — 打包

- [ ] Vue production build
- [ ] FastAPI serve static
- [ ] PyInstaller
- [ ] NeuroDeck.exe
- [ ] 自动创建 SQLite
- [ ] 自动检测 Ollama
- [ ] 自动检测 Codex
- [ ] 自动检测 GPU
- [ ] 自动打开浏览器
- [ ] 系统托盘
- [ ] 开机启动（可选）

最终体验：

```text
NeuroDeck.exe
      ↓
自动启动后台
      ↓
自动打开
http://localhost:5188
```

---

## 16. 第二阶段扩展

后续 Collector：

```text
ClaudeCodeCollector
GeminiCollector
OpenCodeCollector
OpenAICollector
AnthropicCollector
```

统一继承：

```python
class BaseUsageCollector:
    async def collect(self):
        ...

    async def health_check(self):
        ...

    async def get_usage(self):
        ...
```

这样新 Provider 不需要修改整个系统。

---

## 17. 第三阶段：AI Observability

这一阶段开始逐渐接近 Langfuse。

加入：

```text
Trace
Span
Generation
Tool Call
RAG
Agent
Error
Latency
Cost
```

例如：

```text
User Request
│
├─ Planner
│
├─ RAG
│
├─ Qwen
│
├─ Tool Call
│   └─ .NET API
│
└─ Final Generation
```

UI：

```text
TRACE #2341

Total: 4.81s

Planner        421ms
RAG             82ms
Qwen          2.13s
Tool            92ms
Final         1.82s
```

---

## 18. 第四阶段：Agent / RAG / Tool Monitoring

加入：

```text
Agent Runs
Tool Usage
Tool Failure Rate
RAG Recall
Retrieval Latency
LLM Latency
Token Cost
Prompt Version
```

这时 NeuroDeck 就不再只是一个本地 Token Monitor，而会逐渐变成：

> **Local AI Observability Platform**

---

## 19. 推荐开发顺序

不要一开始直接做完整平台。

正确顺序：

```text
① 获取数据
     ↓
② Collector 稳定
     ↓
③ SQLite
     ↓
④ API
     ↓
⑤ 简单 Dashboard
     ↓
⑥ Realtime
     ↓
⑦ 科幻 UI
     ↓
⑧ Ollama Proxy
     ↓
⑨ 打包 EXE
     ↓
⑩ 扩展 Provider
```

尤其不要第一天就：

```text
做登录
做复杂权限
做 Docker
做 PostgreSQL
做 Kafka
做 Redis
做微服务
做 Langfuse clone
```

NeuroDeck 第一版应该保持极轻。

---

## 20. 第一版明确不做

为了防止项目失控：

```text
× 用户登录
× 多用户
× Cloud
× PostgreSQL
× Redis
× Docker 强依赖
× Agent Trace
× RAG Trace
× Prompt Management
× Evaluation
× Alert System
× Mobile App
```

第一版只回答三个问题：

> **我的 AI 现在跑什么？**

> **用了多少 Token、跑多快？**

> **电脑现在承受多少负载？**

---

## 21. MVP 完成标准

当下面全部满足时，NeuroDeck v0.1 就算完成：

- [ ] 双击/启动 NeuroDeck
- [ ] 浏览器可以打开 Dashboard
- [ ] 自动识别 Ollama
- [ ] 自动识别当前 Ollama 模型
- [ ] 显示 context
- [ ] 显示 token/s
- [ ] 显示 Ollama Token 历史
- [ ] 自动读取 Codex Session
- [ ] 显示 Codex Token
- [ ] 显示 Codex 模型
- [ ] 显示 Codex Session
- [ ] 显示 CPU
- [ ] 显示 RAM
- [ ] 显示 GPU
- [ ] 显示 VRAM
- [ ] 显示 GPU 温度
- [ ] 有 24h Token 曲线
- [ ] 有 GPU 曲线
- [ ] 有模型使用排行榜
- [ ] 重启后历史数据仍然存在
- [ ] 无需修改 Codex 使用方式
- [ ] 默认所有数据只留在本机

---

## 22. 推荐学习路线

这个项目可以顺便作为 Python 实战学习项目。

### 第一阶段

重点学：

```text
Python package
class
dataclass / Pydantic
async / await
httpx
JSON
exception
logging
```

### 第二阶段

重点学：

```text
FastAPI
Dependency Injection
REST
WebSocket
Background Task
```

### 第三阶段

重点学：

```text
SQLite
SQLModel / SQLAlchemy
Repository
Index
Aggregation
```

### 第四阶段

重点学：

```text
watchdog
FileSystem Event
Incremental Parser
process monitoring
hardware metrics
```

### 第五阶段

重点学：

```text
LLM Observability
Token Accounting
Trace
Span
Generation
Provider Adapter
```

---

## 23. 最终产品方向

NeuroDeck 可以逐渐形成三个层次：

```text
Level 1
AI Usage Monitor

Ollama
Codex
Hardware
Tokens
Performance
```

↓

```text
Level 2
AI Command Center

Claude Code
Gemini
OpenCode
OpenAI
Multiple Machines
Models
Cost
Sessions
```

↓

```text
Level 3
AI Observability

Agent
RAG
Tools
Trace
Latency
Evaluation
Errors
```

项目定位可以最终写成：

> **NeuroDeck — Local AI Observability & Command Center**

---

## 24. 最重要的建设原则

**第一：Local First**

所有数据默认留在本机。

**第二：Collector 插件化**

Codex、Ollama 只是第一批 Provider。

**第三：先数据，后 UI**

数据准确比 UI 炫酷重要。

**第四：监控不能影响推理**

NeuroDeck 自己不能大量占用 CPU / GPU / RAM。

**第五：不保存用户内容**

默认只记录 metadata 和 metrics。

**第六：保持轻量**

NeuroDeck 的优势不是做另一个 Langfuse。

它应该是：

> 打开就能用、几乎无配置、资源占用低、本地 AI 用户真正愿意每天开着的监控工具。

---

# v0.1 推荐开发任务

第一轮只完成：

```text
Task 1
Python + FastAPI 项目初始化

Task 2
Ollama /api/ps Collector

Task 3
Codex Session Parser

Task 4
psutil System Collector

Task 5
AMD GPU Collector

Task 6
SQLite

Task 7
Overview API

Task 8
Vue Overview

Task 9
WebSocket

Task 10
打包运行
```

完成这 10 个 Task 后，再决定是否进入 Ollama Proxy、更多 Provider 和 Trace。

