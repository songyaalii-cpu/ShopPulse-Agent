"""Canonical analytical view definitions and metric formulas."""

VIEW_DEFINITIONS = {
    "vw_order_item_detail": """
CREATE VIEW vw_order_item_detail AS
SELECT o.id AS order_id, o.order_no, o.ordered_at, o.paid_at, o.status AS order_status,
       o.channel, o.region, o.customer_id, c.customer_code, c.segment,
       oi.id AS order_item_id, oi.product_id, p.sku, p.name AS product_name,
       p.category, p.subcategory, p.brand, oi.quantity, oi.unit_price,
       oi.unit_cost, oi.discount_amount AS item_discount_amount,
       oi.line_amount,
       (oi.quantity * oi.unit_cost)::numeric(14,2) AS item_cost,
       (oi.line_amount - oi.quantity * oi.unit_cost)::numeric(14,2) AS gross_profit
FROM orders o
JOIN customers c ON c.id = o.customer_id
JOIN order_items oi ON oi.order_id = o.id
JOIN products p ON p.id = oi.product_id
""",
    "vw_daily_product_sales": """
CREATE VIEW vw_daily_product_sales AS
SELECT o.ordered_at::date AS metric_date, oi.product_id, p.sku, p.name AS product_name,
       p.category, COUNT(DISTINCT o.id) AS order_count, SUM(oi.quantity) AS units_sold,
       SUM(oi.quantity * oi.unit_price)::numeric(16,2) AS gmv,
       SUM(oi.line_amount)::numeric(16,2) AS item_net_amount,
       SUM(oi.quantity * oi.unit_cost)::numeric(16,2) AS cost_amount,
       SUM(oi.line_amount - oi.quantity * oi.unit_cost)::numeric(16,2) AS gross_profit
FROM orders o JOIN order_items oi ON oi.order_id=o.id JOIN products p ON p.id=oi.product_id
WHERE o.status <> 'cancelled'
GROUP BY o.ordered_at::date, oi.product_id, p.sku, p.name, p.category
""",
    "vw_daily_channel_metrics": """
CREATE VIEW vw_daily_channel_metrics AS
WITH order_metrics AS (
  SELECT o.ordered_at::date metric_date, o.channel,
         COUNT(*) FILTER (WHERE o.status <> 'cancelled') order_count,
         SUM(o.order_amount) FILTER (WHERE o.status <> 'cancelled') gmv,
         SUM(o.paid_amount) FILTER (WHERE o.status <> 'cancelled') paid_amount
  FROM orders o GROUP BY o.ordered_at::date, o.channel
), refund_metrics AS (
  SELECT r.completed_at::date metric_date, o.channel,
         SUM(r.refund_amount) FILTER (WHERE r.status='completed') refund_amount
  FROM refunds r JOIN orders o ON o.id=r.order_id
  GROUP BY r.completed_at::date, o.channel
), event_metrics AS (
  SELECT occurred_at::date metric_date, channel,
         COUNT(*) FILTER (WHERE event_type='view') views,
         COUNT(*) FILTER (WHERE event_type='purchase') purchases
  FROM user_events GROUP BY occurred_at::date, channel
)
SELECT COALESCE(o.metric_date,r.metric_date,e.metric_date) metric_date,
       COALESCE(o.channel,r.channel,e.channel) channel,
       COALESCE(o.order_count,0) order_count, COALESCE(o.gmv,0)::numeric(16,2) gmv,
       COALESCE(o.paid_amount,0)::numeric(16,2) paid_amount,
       COALESCE(r.refund_amount,0)::numeric(16,2) refund_amount,
       (COALESCE(o.paid_amount,0)-COALESCE(r.refund_amount,0))::numeric(16,2) net_sales,
       CASE WHEN COALESCE(o.order_count,0)=0 THEN 0 ELSE o.paid_amount/o.order_count END::numeric(16,2) average_order_value,
       COALESCE(e.views,0) views, COALESCE(e.purchases,0) purchases,
       CASE WHEN COALESCE(e.views,0)=0 THEN 0 ELSE e.purchases::numeric/e.views END::numeric(12,4) payment_conversion_rate,
       CASE WHEN COALESCE(o.paid_amount,0)=0 THEN 0 ELSE COALESCE(r.refund_amount,0)/o.paid_amount END::numeric(12,4) refund_rate
FROM order_metrics o FULL JOIN refund_metrics r USING(metric_date,channel)
FULL JOIN event_metrics e ON e.metric_date=COALESCE(o.metric_date,r.metric_date) AND e.channel=COALESCE(o.channel,r.channel)
""",
    "vw_customer_lifetime_value": """
CREATE VIEW vw_customer_lifetime_value AS
WITH order_totals AS (
  SELECT customer_id, COUNT(*) FILTER (WHERE status<>'cancelled') order_count,
         SUM(paid_amount) FILTER (WHERE status<>'cancelled') paid_amount,
         MIN(ordered_at) first_order_at, MAX(ordered_at) last_order_at
  FROM orders GROUP BY customer_id
), refund_totals AS (
  SELECT customer_id, SUM(refund_amount) FILTER (WHERE status='completed') refund_amount
  FROM refunds GROUP BY customer_id
)
SELECT c.id customer_id, c.customer_code, c.segment, c.region,
       COALESCE(o.order_count,0) order_count,
       COALESCE(o.paid_amount,0)::numeric(16,2) paid_amount,
       COALESCE(r.refund_amount,0)::numeric(16,2) refund_amount,
       (COALESCE(o.paid_amount,0)-COALESCE(r.refund_amount,0))::numeric(16,2) net_sales,
       o.first_order_at, o.last_order_at
FROM customers c LEFT JOIN order_totals o ON o.customer_id=c.id
LEFT JOIN refund_totals r ON r.customer_id=c.id
""",
    "vw_behavior_funnel_daily": """
CREATE VIEW vw_behavior_funnel_daily AS
SELECT occurred_at::date metric_date, channel,
       COUNT(DISTINCT session_id) sessions,
       COUNT(*) FILTER (WHERE event_type='view') views,
       COUNT(*) FILTER (WHERE event_type='click') clicks,
       COUNT(*) FILTER (WHERE event_type='add_to_cart') add_to_carts,
       COUNT(*) FILTER (WHERE event_type='checkout') checkouts,
       COUNT(*) FILTER (WHERE event_type='purchase') purchases,
       CASE WHEN COUNT(*) FILTER (WHERE event_type='view')=0 THEN 0
            ELSE (COUNT(*) FILTER (WHERE event_type='purchase'))::numeric /
                 COUNT(*) FILTER (WHERE event_type='view') END::numeric(12,4) payment_conversion_rate
FROM user_events GROUP BY occurred_at::date, channel
""",
}
