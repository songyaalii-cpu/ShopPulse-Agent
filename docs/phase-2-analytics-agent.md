# ShopPulse 第二阶段经营分析 Agent

## 架构

第二阶段采用“PostgreSQL/Python 确定性计算 + LangGraph 显式编排 + 可选 LLM 表达”。无模型
API Key 时，全部分析和 Markdown 周报仍可运行。

```mermaid
flowchart TD
  S[START] --> P[parse_request]
  P --> I[select_analysis]
  I --> B[build_plan]
  B --> X[execute_metric]
  X -->|普通分析| W[write_answer]
  X -->|异常归因| A[detect_anomaly]
  A --> C[choose_drilldown]
  C -->|深度小于3且调用小于8| D[execute_drilldown]
  D --> C
  C -->|停止| V[validate_evidence]
  V --> W
  X -->|错误| H[handle_error]
  W --> E[END]
  H --> E
```

State 明确保存原问题、结构化请求、意图、当前/对比区间、过滤条件、指标、计划、工具结果、
异常、下钻历史、证据、警告、重试和调用次数及最终回答。隐藏推理过程不会记录。

## 指标与时间

指标注册表位于 `shoppulse/analytics/metrics.py`。GMV、订单量、实付、退款、净销售、客单价、
毛利、毛利率、退款率和支付转化率沿用第一阶段口径。订单、退款、明细和事件先分别聚合，避免
Join 放大；空分母返回 0。日期默认锚定数据库最大业务日期，趋势默认 12 周，周从周一开始。

## RFM、Cohort 与漏斗

- RFM 参考日为最大业务日期后一天；R 越近越高，F/M 越大越高，使用稳定 `NTILE(5)`，规则固定
  为 Champions、Loyal Customers、Potential Loyalists、New Customers、At Risk、Hibernating、
  Lost 和 Others；默认只返回客户业务编号样本，不返回邮箱或手机号。
- Cohort 月是首次有效支付月，活跃月按自然月，输出 M0-M11 人数与留存；未来尚不可观测格为
  `null`，历史无活跃才是 0。
- 漏斗按 `session_id` 去重并检查 view→click→add_to_cart→checkout→purchase 顺序，支持日/周、
  渠道、设备、地区、活动和品类过滤。

## 异常与归因

异常检测使用至少 8 个历史周期的滚动中位数和 MAD；MAD 为零时降级为标准差或相对变化。
结果包含基线、绝对/相对变化、稳健分数、方向、严重程度、算法和完整性。历史不足会返回
`insufficient_history`，不会猜测。

归因维度只允许 region、channel、category、segment、campaign、device_type。数值指标按维度
贡献变化排序；退款率、客单价和支付转化率同时保留分子/分母证据。Graph 最多下钻 3 层、最多
8 次工具调用、每层返回前 5 个贡献项。结果描述贡献和相关性，不宣称因果。

第一阶段注入的验收信号：南区退款率上升、social 转化下降、SP-00007 缺货。运行时提示词不含
这些答案，测试只根据数据验证能否发现。

## 周报与增强分析

经营周报使用数据最大日期所在最新完整周，并与上一完整周比较，包含 KPI、RFM、Cohort、漏斗、
异常维度、风险、建议和限制。模板化 Markdown 是无模型降级结果。商品关联提供 support、confidence、
lift；库存预警提供 7/14/30 日销量、可售天数、缺货/低库存/积压标记，全程只读。

## 启动和示例

```bash
docker-compose up -d --wait postgres
uv run alembic upgrade head
uv run shoppulse-analyze "展示最近12周GMV、订单量和客单价趋势"
uv run shoppulse-analyze "对客户进行RFM分群"
uv run shoppulse-analyze "分析最近六个月新客次月留存"
uv run shoppulse-analyze "比较各渠道浏览到支付的转化率"
uv run shoppulse-analyze "为什么最近一周退款率上升？"
uv run shoppulse-analyze "生成最新完整周经营周报" --format markdown
uv run langgraph dev --no-browser
```

## 测试与评测

```bash
uv run pytest -q tests/analytics
TEST_DATABASE_URL=postgresql+psycopg://shoppulse:shoppulse_local_only@localhost:5432/shoppulse_test uv run pytest -q
uv run shoppulse-analytics-eval
```

20 条本地评测覆盖趋势、RFM、Cohort、漏斗、异常归因和周报，输出意图准确率、工具选择、
指标命中、异常方向、归因维度、平均工具次数和耗时；不依赖 LLM-as-Judge。

## 安全与限制

固定分析查询使用绑定参数；动态维度和过滤均来自白名单，Agent 无 DDL/DML 工具。错误不返回连接
URL，默认输出不含 PII。品类归因将一个订单归属到金额最高的主品类以保持订单指标可加总，属于
解释性近似；普通 View 尚未物化；统计归因不能替代实验、活动日志或业务调查。
