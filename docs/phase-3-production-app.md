# Phase 3：可部署、流式、可追踪与可评测应用

ShopPulse 第三阶段把第二阶段的显式 LangGraph 工作流包装成完整应用。经营查询仍使用只读
SQL 语义层；API 不在请求进程中长时间运行图，PostgreSQL 是历史事实来源，Redis 只承担队列、
实时事件与短期缓存。本项目基于 Apache 2.0 的 LangSmith Agent Lifecycle Workshop 二次开发。

## 架构与职责

```mermaid
flowchart LR
  W["Next.js Web"] -->|REST| A["FastAPI API"]
  W -->|SSE| A
  A -->|会话、任务、事件| P[("PostgreSQL 16")]
  A -->|ARQ 投递| R[("Redis 7")]
  R --> K["独立 Worker"]
  K --> G["Analytics StateGraph"]
  G -->|只读分析| P
  K -->|结果和历史事件| P
  K -->|实时 Stream / Cache| R
```

- `api`：验证请求、所有权、幂等键与分页；任务先落库再入队。
- `worker`：ARQ 消费任务、设置 lease、执行现有 StateGraph、持久化安全结果。
- `postgres`：八张经营表及 `agent_sessions`、`analysis_runs`、`analysis_run_events`、
  `evaluation_runs`；Redis 丢失不影响完成历史。
- `redis`：队列 `shoppulse:queue`、事件 `shoppulse:events:{run_id}`、结果缓存
  `shoppulse:analysis:v1:{sha256}`。Stream 有最大长度和 TTL，缓存只保存成功的确定性结果。
- `frontend`：App Router 页面和框架无关图表契约的 ECharts 适配。

## API

| 方法 | 路径 | 用途 |
|---|---|---|
| GET | `/health/live`, `/health/ready` | 进程及 PostgreSQL/Redis 就绪 |
| POST/GET | `/api/v1/sessions` | 创建、分页列出会话 |
| GET/DELETE | `/api/v1/sessions/{session_id}` | 会话详情/级联删除 |
| POST | `/api/v1/sessions/{session_id}/runs` | 以 `Idempotency-Key` 提交任务 |
| GET | `/api/v1/sessions/{session_id}/runs` | 分页历史 |
| GET | `/api/v1/runs/{run_id}` | 状态、结果、Token、成本 |
| POST | `/api/v1/runs/{run_id}/cancel` | 取消 queued/running 任务 |
| GET | `/api/v1/runs/{run_id}/events` | SSE 历史补发与实时流 |
| POST/GET | `/api/v1/evaluations[/{id}]` | 异步评测及报告 |

统一错误包含 `code`、安全 `message`、`request_id` 和 `retryable`，不返回堆栈或连接 URL。
任务提交默认按客户端每分钟 30 次限流，超限返回 429，可用环境变量调整。
演示身份来自 `X-Client-ID`（EventSource 可用 `client_id` query）；它不是正式认证机制。

## SSE 与任务状态机

事件体固定包含 `event_id/run_id/sequence/event_type/timestamp/node_name/payload`。支持
`run.queued`、`run.started`、`graph.node.started/completed`、`tool.started/completed`、
`analysis.partial`、`chart.ready`、`run.completed/failed/cancelled` 和 `heartbeat`。工具事件只给
名称、耗时和摘要，不发送隐藏推理。`Last-Event-ID` 先在 PostgreSQL 找 sequence，再补发后续事件；
客户端断开不会取消任务。

```mermaid
stateDiagram-v2
  [*] --> queued
  queued --> running
  queued --> cancelled
  running --> completed
  running --> failed
  running --> cancelled
  running --> queued: lease 超时恢复
```

ARQ 最多尝试 `RUN_MAX_RETRIES + 1` 次；参数和明确业务错误不重试。运行任务持有
`lease_expires_at`，定时恢复器重新投递超时任务。`run_id` 同时是队列 job ID；数据库状态锁和
会话内幂等键防止重复执行。

## 图表契约与指标口径

后端返回 `chart_id/chart_type/title/x_axis/categories/series/rows/metadata`，不返回 ECharts option。
前端适配 line、bar、heatmap、funnel、table、graph。当前展示 KPI 趋势、RFM、Cohort 热力图、
行为漏斗、三层归因、库存预警和商品关联。Cohort 未成熟单元格保持 `null`，不当作 0。

经营指标继续以 Phase 2 文档为唯一口径：GMV 是非取消订单原价金额，净销售额是实付减已完成退款，
退款率是已完成退款/实付，客单价是实付/有效订单，毛利是明细收入减数量×单位成本。

## Token、成本与评测

模型 usage 只读取响应 metadata；无模型为 0，模型未返回 usage 为 unknown (`null`)。价格集中在
`shoppulse/evals/pricing.json`，包含币种和生效日；未知模型成本为 `null`，不会套用其他价格。

`shoppulse/evals/dataset.json` 有 72 条无隐私样本：趋势 12、RFM 10、Cohort 10、漏斗 10、
异常归因 18、周报 6、库存 3、关联 3。默认评测无需模型 Key，输出 JSON、Markdown、分意图、
失败、最慢和最贵案例。SQL 执行准确率定义为“成功执行且结构符合预期的数据库任务 / 需要数据库
执行的任务”；语义和答案正确率还检查指标、数值、方向、维度、证据及禁止结论。

```bash
uv run shoppulse-eval --output-dir reports/phase3
```

## 启动、开发与测试

```bash
cp .env.example .env
docker-compose up --build --wait
docker-compose ps
curl --fail http://localhost:8000/health/ready
curl --fail http://localhost:3000
```

API/Worker 使用非 root Python 3.11 镜像，前端使用 Node 多阶段构建。生产环境必须显式提供独立
数据库凭据和 `DEMO_USER_ID`，密钥只从服务端环境变量读取。

```bash
uv sync --group dev
TEST_DATABASE_URL=postgresql+psycopg://shoppulse:...@localhost:5432/shoppulse_test uv run pytest
cd frontend && npm test && npm run build
```

故障排查：`/health/ready` 503 时检查 `docker-compose ps`；队列不可用时用相同幂等键重试；
任务长期 running 时检查 worker health key 和 lease 恢复日志；SSE 重连传 `Last-Event-ID`；数据库
重建后删除 `shoppulse:analysis:v1:*` 使缓存整体失效。

## 当前限制

- 演示 `X-Client-ID` 不是登录认证；公网部署前必须接入身份提供方、授权和限流网关。
- 本地使用单 Redis；高可用 Redis/PostgreSQL、对象存储和 Kubernetes 不在本阶段。
- 节点事件来自 LangGraph update stream；不包含隐藏推理，也不承诺模型供应商内部阶段。
- 成本价格表默认为空，只有显式配置已知模型后才估算。
- LangSmith 可选，本地启动和评测不依赖它。
