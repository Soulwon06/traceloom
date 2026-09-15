<p align="center">
  <img src="docs/assets/logo.png" alt="TraceLoom logo" width="160">
</p>

# TraceLoom

## Readable Observability for AI Applications

看见运行过程，也看懂它。

TraceLoom 是一个本地可读性观测工具：捕获 Python 应用运行时的 HTTP 请求、LLM 调用、测试、日志和异常，并把它们组织成可筛选、可回看的事件时间线。

[![GitHub](https://img.shields.io/badge/GitHub-Soulwon06%2Ftraceloom-181717?logo=github)](https://github.com/Soulwon06/traceloom)

## 为什么做 TraceLoom

AI 应用的一次结果，往往经过多次 HTTP 调用、模型请求、工具交互和业务代码。TraceLoom 把这些运行时行为放在同一个本地 Dashboard 中，让开发者可以从摘要进入完整事件，再回到原始请求和响应核对细节。

它是可读的运行时记录层，不是自动根因分析器，也不会替业务日志或测试系统。

## 界面预览

![TraceLoom Dashboard](docs/assets/screenshot.png)

上图来自仓库中的本地 OpenAI 风格 Mock 请求，展示了 HTTP 事件、请求/响应详情，以及 LLM View 中的模型、服务商、消息、结束原因和 Token Usage。

## 当前已实现

- 捕获 `requests`、`httpx`、`aiohttp`、gRPC 和 `botocore` 的出站请求
- 通过 FastAPI、Django 中间件捕获入站请求
- 捕获 pytest 测试执行、结果、耗时、fixture 和失败信息
- 可选捕获 Python `logging`；捕获未处理异常、traceback 和源代码位置
- 记录运行时父子关系，并支持 `--app`、`--session` 标记
- Dashboard 与 JSON API 支持按类型、方法、主机、状态、应用和会话筛选
- 支持对事件摘要和事件数据进行关键词文本搜索
- 识别 OpenAI、Anthropic、Gemini 格式，并提供统一的 LLM 可读视图
- LLM View 可展示 system prompt、消息、tool use、tool result、thinking、图片块、结束原因和 Token metadata（以原始数据为准）
- 保留 Raw / Tree 视图，便于核对原始结构
- 默认使用本地 SQLite 保存事件

LLM View 是阅读层：它不改变 Provider 的原始格式，也不把不同 Provider 的字段强行当成同一种语义。

## 快速开始

### 运行时要求

- Python 3.14+（TraceLoom Server 当前要求 Python 3.14+）
- [uv](https://docs.astral.sh/uv/)（推荐用于仓库安装和可复现运行）
- Node.js 22+ 仅在本地运行前端开发服务器时需要

### 启动 Dashboard

```bash
git clone https://github.com/Soulwon06/traceloom.git
cd traceloom
uv sync --frozen
```

终端一启动 API Server：

```bash
uv run traceloom-server --no-open
```

默认监听 `127.0.0.1:5110`，数据保存在 `~/.traceloom/traceloom.db`。

终端二启动前端：

```bash
cd frontend
npm ci
npm run dev
```

前端开发服务器默认运行在 `http://127.0.0.1:5111`，并把 `/api` 请求代理到本地 Server。

### 运行你的 Python 程序

回到仓库根目录，在终端三运行：

```bash
uv run traceloom run my_app.py
```

也可以运行测试或 ASGI 应用：

```bash
uv run traceloom run pytest tests/
uv run traceloom run uvicorn app:app
```

如果客户端与 Server 不在默认地址，使用 `--server`：

```bash
uv run traceloom run --server http://localhost:5110 -- python -m my_module
```

`traceloom run` 会在被包装的进程启动前激活客户端；不需要修改业务代码。也可以在代码中显式调用：

```python
import traceloom

traceloom.init(server_url="http://localhost:5110")
```

### 本地 LLM Mock 示例

该示例不会访问真实模型服务、不需要 API Key：

```bash
uv run traceloom run examples/python/llm_mock_request.py
```

选择 Dashboard 中的 `POST /v1/chat/completions` 事件，可以看到请求消息、模拟响应和 LLM View。

## LLM 可读视图

当请求或响应符合已支持的 Provider 格式时，Body Viewer 提供 `LLM`、`Tree` 和 `Raw` 视图。LLM View 将原始 JSON 中可识别的内容整理为：

- Model 与 Provider
- System Prompt、User、Assistant 消息
- Tool Use、Tool Result、Thinking 和图片块（如果存在）
- Finish Reason
- Input / Output Token，以及可用的 thinking/cache metadata

统一视图用于快速阅读；遇到字段含义不明确时，应回到 `Tree` 或 `Raw` 查看原始数据。

## 数据流

```text
Python 应用
    │
    ├─ HTTP client patch / framework middleware
    ├─ pytest / logging / exception hooks
    │
    ▼
TraceLoom Python Client ── HTTP ──▶ TraceLoom Server ──▶ SQLite
                                           │
                              Dashboard / JSON API / traceloom query
```

TraceLoom Server 是本地 API 和事件存储服务；Dashboard 是前端展示层。客户端捕获的数据通过 Server 进入同一条事件时间线。

## 配置与查询

`traceloom run` 的主要配置也可以通过 `TRACELOOM_*` 环境变量设置。常用选项包括：

| 目的 | CLI | 环境变量 |
| --- | --- | --- |
| Server 地址 | `--server URL` | `TRACELOOM_URL` |
| 只捕获指定主机 | `--capture-host HOST` | `TRACELOOM_CAPTURE_HOSTS` |
| 忽略主机 | `--ignore-host HOST` | `TRACELOOM_IGNORE_HOSTS` |
| 脱敏 Header | `--redact-header HEADER` | `TRACELOOM_REDACT_HEADERS` |
| 脱敏查询参数 | `--redact-query-param PARAM` | `TRACELOOM_REDACT_QUERY_PARAMS` |
| 应用/会话标记 | `--app NAME` / `--session ID` | `TRACELOOM_APP` / `TRACELOOM_SESSION` |

终端查询：

```bash
uv run traceloom query
uv run traceloom query --type http --status 500 --ancestors
uv run traceloom meta
```

详见 [配置文档](docs/configuration.md)、[查询文档](docs/query.md) 和 [API 文档](docs/api.md)。

## 隐私边界

TraceLoom 默认用于本机开发调试，请在启动前确认被捕获数据适合存储。

- 客户端默认将 `Authorization`、`X-Api-Key`、`X-Goog-Api-Key` Header 值替换为 `[REDACTED]`。
- 请求/响应 Body 不是自动安全的：Prompt、Token、个人数据和业务数据可能被原样保存。
- Cookie、响应 Body、查询参数和异常帧中的源代码不会因为默认 Header 脱敏而自动消失。
- 查询参数默认不脱敏；用 `TRACELOOM_REDACT_QUERY_PARAMS` 或 `--redact-query-param` 明确配置需要隐藏的参数。
- Server 默认绑定 `127.0.0.1`，默认保留七天事件；设置 `TRACELOOM_RETENTION_DAYS=0` 可关闭自动清理。
- `--host 0.0.0.0` 会允许局域网访问。V1 API 没有内置身份认证，只应在可信网络中使用，不应直接暴露到公网。

## 项目状态

TraceLoom V1 当前聚焦于“让运行时行为可见且可读”：本地捕获、事件时间线、详情面板、关键词查询和 LLM 可读视图已经实现。

## Roadmap

以下方向不属于当前 V1 的已实现能力：

- AI Root Cause Analysis
- RAG Debugger
- AI Request Journey
- Retry / Fallback Analysis
- Cost / Performance Analysis
- Semantic / AI Search
- Complex Query Builder
- Complex Distributed Tracing
- Large Evaluation System

因此，TraceLoom V1 不宣称自动根因结论、语义搜索、向量检索、成本计算或复杂分布式追踪。

## 开发

安装仓库依赖：

```bash
uv sync --frozen
```

运行 Python 全量测试：

```bash
pytest
```

运行前端检查：

```bash
cd frontend
npm ci
npm run test
npm run build
npm run lint
```

更多调试指南位于 [docs/](docs/index.md)；仓库内的 [TraceLoom Skill](skills/traceloom/SKILL.md) 和 [Setup Skill](skills/traceloom-setup/SKILL.md) 用于辅助调试和接入。

## 法律与致谢

TraceLoom 以 MIT License 发布，详见 [LICENSE](LICENSE)。

TraceLoom 的早期产品探索和部分实现基础来自 MIT-licensed 开源项目 Smello。本仓库保留相关 upstream attribution，并遵循适用的开源许可证要求，详见 [THIRD_PARTY_NOTICES.md](THIRD_PARTY_NOTICES.md)。

## 版本记录

变更记录见 [CHANGELOG.md](CHANGELOG.md)。
