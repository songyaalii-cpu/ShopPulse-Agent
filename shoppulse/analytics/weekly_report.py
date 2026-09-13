"""Evidence-backed weekly operations report with a no-model Markdown fallback."""

from datetime import timedelta
from typing import Any

from sqlalchemy import Engine

from shoppulse.analytics.attribution import multi_dimensional_attribution
from shoppulse.analytics.cohort import cohort_retention
from shoppulse.analytics.funnel import funnel_analysis
from shoppulse.analytics.metrics import metric_trend
from shoppulse.analytics.periods import complete_week_end, data_max_date
from shoppulse.analytics.rfm import rfm_segments
from shoppulse.analytics.schemas import DatePeriod
from shoppulse.db.session import get_engine


def _one_week(start, end, engine):
    result = metric_trend(start, end, "week", engine=engine)
    return result["rows"][0] if result["rows"] else {}


def _change(current: float, previous: float) -> float:
    return (current - previous) / abs(previous) if previous else (1.0 if current else 0.0)


def weekly_report(engine: Engine | None = None) -> dict[str, Any]:
    db = engine or get_engine()
    end = complete_week_end(data_max_date(db))
    current = DatePeriod(start=end - timedelta(days=6), end=end, granularity="week")
    previous = DatePeriod(start=end - timedelta(days=13), end=end - timedelta(days=7), granularity="week")
    current_kpis = _one_week(current.start, current.end, db)
    previous_kpis = _one_week(previous.start, previous.end, db)
    changes = {key: _change(float(current_kpis.get(key, 0)), float(previous_kpis.get(key, 0))) for key in (
        "gmv", "order_count", "average_order_value", "refund_rate", "payment_conversion_rate", "gross_margin"
    )}
    primary_metric = max(changes, key=lambda key: abs(changes[key]))
    attribution = multi_dimensional_attribution(
        primary_metric, current, previous, ["region", "channel", "category"], max_depth=3, engine=db
    )
    rfm = rfm_segments(db)
    cohort = cohort_retention(db, months=2)
    funnel_current = funnel_analysis(current.start, current.end, "week", engine=db)
    funnel_previous = funnel_analysis(previous.start, previous.end, "week", engine=db)
    risks = []
    if changes["refund_rate"] > 0.15:
        risks.append("退款率环比显著上升，建议复核主要贡献地区与品类。")
    if changes["payment_conversion_rate"] < -0.15:
        risks.append("支付转化率环比显著下降，建议排查渠道流量质量与结算链路。")
    if not risks:
        risks.append("未检测到超过 15% 环比阈值的退款率或支付转化异常。")
    markdown = (
        f"# ShopPulse 经营周报（{current.start} 至 {current.end}）\n\n"
        f"## 数据事实\n- GMV：{current_kpis.get('gmv', 0):,.2f}（环比 {changes['gmv']:+.1%}）\n"
        f"- 订单量：{current_kpis.get('order_count', 0)}（环比 {changes['order_count']:+.1%}）\n"
        f"- 客单价：{current_kpis.get('average_order_value', 0):,.2f}（环比 {changes['average_order_value']:+.1%}）\n"
        f"- 退款率：{current_kpis.get('refund_rate', 0):.2%}（环比 {changes['refund_rate']:+.1%}）\n"
        f"- 支付转化率：{current_kpis.get('payment_conversion_rate', 0):.2%}（环比 {changes['payment_conversion_rate']:+.1%}）\n\n"
        f"## 分析判断\n本周相对变化最大的指标是 `{primary_metric}`；维度拆解仅表示贡献与相关性，不证明因果。\n\n"
        f"## 风险与动作\n" + "\n".join(f"- {risk}" for risk in risks) +
        "\n- 对首要贡献维度进行活动、商品和用户层复核，并结合实验或业务日志验证原因。\n\n"
        "## 数据限制\n- 周报基于模拟数据最大日期所在完整周；退款按完成日期归属。\n"
    )
    return {
        "period": current.model_dump(mode="json"), "comparison_period": previous.model_dump(mode="json"),
        "metrics": current_kpis, "changes": changes, "primary_metric": primary_metric,
        "attribution": attribution, "rfm": rfm, "cohort": cohort,
        "funnel": {"current": funnel_current["totals"], "previous": funnel_previous["totals"]},
        "risks": risks, "recommendations": ["复核首要贡献维度", "用活动或业务日志验证相关性"],
        "limitations": ["Contribution is not causal proof.", "Synthetic data uses its own maximum business date."],
        "markdown": markdown,
    }
