# ShopPulse 第一阶段数据平台

## 范围与架构

第一阶段只建立工程环境、PostgreSQL 业务数据层和分析数据集。LangGraph checkpoint/memory
通过 `LANGGRAPH_DATABASE_URL` 预留，业务访问层绝不读取它；Agent 推理、前端和推荐系统不在本阶段。

```mermaid
flowchart LR
    SQLite["保留的 TechHub SQLite\n回归/迁移源"] --> Importer["幂等导入器\n校验 + 显式类型转换"]
    Generator["固定种子生成器\n业务规律 + 异常注入"] --> Loader["安全重建 + 批量写入"]
    Importer --> PG[("PostgreSQL 16\nShopPulse 业务库")]
    Loader --> PG
    Alembic["Alembic schema migrations"] --> PG
    PG --> DAL["SQLAlchemy 2.0\nengine/session/transaction"]
    DAL --> Tools["参数化数据库工具"]
    PG --> Views["5 个分析 View"]
    Views --> ReadOnly["Text-to-SQL 只读边界\nAST + timeout + row limit"]
    PG --> Quality["数据质量检查"]
    State[("LangGraph 状态库\n仅预留配置")] -. 后续阶段 .-> Agent["LangGraph Agent"]
```

## 表关系

```mermaid
erDiagram
    CUSTOMERS ||--o{ ORDERS : places
    MARKETING_CAMPAIGNS o|--o{ ORDERS : attributes
    ORDERS ||--|{ ORDER_ITEMS : contains
    PRODUCTS ||--o{ ORDER_ITEMS : sold_as
    ORDERS ||--o{ REFUNDS : has
    ORDER_ITEMS o|--o{ REFUNDS : item_scope
    CUSTOMERS ||--o{ REFUNDS : requests
    PRODUCTS ||--o{ INVENTORY_SNAPSHOTS : stocked
    CUSTOMERS o|--o{ USER_EVENTS : performs
    PRODUCTS o|--o{ USER_EVENTS : concerns
    MARKETING_CAMPAIGNS o|--o{ USER_EVENTS : influences
```

八张业务表使用 BigInteger 主键；`customer_code`、`sku`、`order_no`、`refund_no`、
`event_id` 和 `campaign_code` 是唯一业务编号。所有金额均为 `NUMERIC(14,2)`/Python
`Decimal`。外键默认限制误删，事件等可选维度采用 `SET NULL`，订单明细随订单级联。

核心字段如下：

| 表 | 主维度/事实 | 高频索引与约束 |
|---|---|---|
| `customers` | 会员、地区、省市、分层、注册渠道/时间 | code/email 唯一；地区+分层、注册时间 |
| `products` | SKU、类目、品牌、标价/售价/成本、状态 | SKU 唯一；类目+状态；售价≤标价、成本≤售价 |
| `marketing_campaigns` | 类型、渠道、预算、起止时间、状态 | code 唯一；渠道+时间；结束晚于开始 |
| `orders` | 客户/活动、渠道、状态、地区、订单/折扣/运费/实付 | order_no 唯一；客户/渠道/状态/地区+下单时间；实付公式 |
| `order_items` | 商品、数量、成交价、成本、折扣、行金额 | 订单+商品唯一；行金额公式 |
| `refunds` | 订单/明细/客户、原因、类型、状态、金额和时间 | refund_no 唯一；订单+状态、客户+申请时间 |
| `inventory_snapshots` | 商品、仓库、可用/预留/在途、快照日 | 商品+仓库+日期唯一 |
| `user_events` | 会话、客户/商品/活动、事件、渠道、设备、JSONB 属性 | event_id 唯一；会话/客户/商品/活动+时间 |

`properties` 当前没有稳定的 JSON 路径查询，因此没有滥建 GIN 索引；明确查询需求出现后再以
表达式索引或 `jsonb_path_ops` GIN 补充。

## 时区策略

事件和业务时间统一使用 PostgreSQL `TIMESTAMPTZ`，生成器与迁移器写入 UTC。数据库连接返回
带时区时间；报表展示层后续按业务时区（默认 `Asia/Shanghai`）转换。纯日粒度库存使用 `DATE`。

## 环境变量

| 变量 | 用途 | 本地默认 |
|---|---|---|
| `DATABASE_URL` | ShopPulse 业务库 SQLAlchemy URL | `postgresql+psycopg://.../shoppulse` |
| `LANGGRAPH_DATABASE_URL` | 后续 checkpoint/memory；本阶段不使用 | 可空/示例值 |
| `POSTGRES_DB/USER/PASSWORD/PORT` | Compose PostgreSQL | 仅适合本机的弱默认值 |
| `DB_POOL_SIZE` / `DB_MAX_OVERFLOW` | 连接池 | 5 / 10 |
| `DB_POOL_TIMEOUT_SECONDS` | 取连接超时 | 30 |
| `SQL_QUERY_TIMEOUT_MS` | 动态 SQL 执行超时 | 5000 |
| `SQL_MAX_ROWS` | 动态 SQL 最大返回行数 | 200 |
| `APP_ENV` | reset 生产保护 | `development` |

`.env` 被 Git 忽略；只提交 `.env.example`。本地默认密码不得复用于生产环境。

## 启动、迁移与健康检查

```bash
cp .env.example .env
uv sync --group dev
docker-compose up -d --wait postgres
docker-compose exec postgres pg_isready -U "${POSTGRES_USER:-shoppulse}" -d "${POSTGRES_DB:-shoppulse}"
uv run shoppulse-wait-db --timeout 60
uv run alembic upgrade head
uv run alembic current
```

初始化命令必须在 `shoppulse-wait-db` 成功后运行。数据由命名 volume
`shoppulse_postgres_data` 持久化。回滚仅用于开发/测试：`uv run alembic downgrade base`。

## SQLite 导入

原文件 `data/structured/techhub.db` 保留且不删除。导入映射为：`customer_id→customer_code`、
`product_id→sku`、`order_id→order_no`，旧整数明细主键保持不变；其他主键采用稳定排序映射。
SQLite `REAL` 先经字符串再转 `Decimal(0.01)`，日期明确加 UTC。

```bash
uv run shoppulse-migrate-sqlite --dry-run
uv run shoppulse-migrate-sqlite
uv run shoppulse-migrate-sqlite --validate-only
```

导入在单个 PostgreSQL 事务中执行，业务唯一键使用 `ON CONFLICT DO UPDATE`，重复运行不增行；
失败自动回滚。源端先检查外键、空业务号、重复号和订单金额，命令输出源/目标前后计数。

## 模拟数据

默认规模为 2,000 客户、200 商品、20,000 订单、约 40,000–80,000 明细、约 2,600
退款、30 活动、13 个月×2 仓的库存快照和 200,000 行为事件。

```bash
uv run shoppulse-generate --preview --seed 20260804
uv run shoppulse-generate --reset --confirm-reset shoppulse --seed 20260804
# 小规模示例
uv run shoppulse-generate --customers 200 --products 50 --orders 1000 \
  --campaigns 10 --events 8000 --months 12 --seed 42 --reset --confirm-reset shoppulse
```

相同参数和 seed 生成完全相同的业务行与 SHA-256 指纹。`--reset` 只允许
`shoppulse`、`shoppulse_dev`、`shoppulse_test`，拒绝 `APP_ENV=production`，且确认值必须精确等于
数据库名。

数据规律：周末、节假日和活动期提高订单权重；渠道、地区、类目价格有差异；成本占售价
48%–72%；高价值前 20% 客户获得约 55% 下单权重；完整会话严格按浏览→点击→加购→结算→支付；
服饰退款基准更高；活动提高对应渠道流量/订单归因；库存随累计销售减少并在低位产生在途。

已注入且可解释的异常：

1. 最后 60 天南区退款抽样权重提升 3.5 倍（地区退款率异常）。
2. 最后 45 天 social 渠道放弃会话最多到 click（支付转化下降）。
3. `SP-00007` 最后两个库存快照可用库存为 0（缺货影响销量/漏斗）。

## 分析视图和统一指标口径

| View | 粒度 | 用途 |
|---|---|---|
| `vw_order_item_detail` | 订单明细 | 客户/商品/渠道宽表、行成本和毛利 |
| `vw_daily_product_sales` | 日期×商品 | 销量、GMV、行净额、成本、毛利 |
| `vw_daily_channel_metrics` | 日期×渠道 | GMV、实付、退款、净销售、客单价、转化率 |
| `vw_customer_lifetime_value` | 客户 | 累计订单、实付、退款、净销售 |
| `vw_behavior_funnel_daily` | 日期×渠道 | 会话及五阶段漏斗 |

- GMV：非取消订单的 `order_amount`（折扣前商品成交金额，不含运费）。
- 实付金额：非取消订单 `paid_amount = order_amount - discount_amount + shipping_fee`。
- 退款金额：状态为 `completed` 的 `refund_amount`。
- 净销售额：实付金额 − 已完成退款金额。
- 客单价：实付金额 ÷ 非取消订单数。
- 毛利：Σ(`line_amount - quantity × unit_cost`)；当前不分摊运费和营销费。
- 退款率：已完成退款金额 ÷ 实付金额。
- 支付转化率：purchase 事件数 ÷ view 事件数（同日同渠道基础口径）。

## SQL 安全与质量检查

Agent 自有查询全部使用 SQLAlchemy bind parameters。Text-to-SQL 入口先用 PostgreSQL AST 验证单条
Query，拒绝 INSERT、UPDATE、DELETE、DROP、ALTER、TRUNCATE、CREATE、GRANT、REVOKE、COPY、
数据修改 CTE、锁行与危险函数；随后开启 `READ ONLY` 事务、设置 `statement_timeout`，并以外层
`LIMIT` 强制最大行数。

```bash
uv run shoppulse-quality
```

质量报告包含八表计数、孤立外键、重复业务号、异常空值、订单/明细金额不一致、超额退款、
事件时序异常及 GMV/实付/退款/净销售/客单价/毛利摘要；关键问题非零时命令退出 1。

## 测试

```bash
uv run pytest -q
# PostgreSQL 集成测试必须使用可销毁、库名以 _test 结尾的数据库
createdb shoppulse_test
TEST_DATABASE_URL=postgresql+psycopg://shoppulse:shoppulse_local_only@localhost:5432/shoppulse_test uv run pytest -q
```

集成测试覆盖连接、空库 `upgrade head`、幂等 SQLite 导入、工具回归、小规模生成、外键/唯一与
金额约束、退款上限、事件时序和质量报告。没有 `TEST_DATABASE_URL` 时仅跳过 PostgreSQL 集成用例。

## 当前限制与下一阶段

- 第一阶段没有复杂经营分析 Agent、前端、推荐系统或 LangGraph 持久化实现。
- 分析 View 是实时普通视图；数据量和查询负载稳定后再依据 `EXPLAIN ANALYZE` 决定物化策略。
- JSONB 暂无稳定谓词，所以不建 GIN；退款总额上限等跨行规则由生成/质量层校验，后续可增加触发器。
- 生成器是分析验证数据，不包含真实个人信息，不应用于财务记账或生产容量估算。

第二阶段建议：先定义经营问题/指标语义层与 Agent 工具契约；再实现带权限和可观测性的分析
LangGraph；最后建立基于已注入异常的归因评测集和 LangSmith 回归门禁。
