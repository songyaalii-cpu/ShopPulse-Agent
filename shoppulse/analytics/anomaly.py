"""Robust, deterministic anomaly detection for KPI time series."""

from __future__ import annotations

from statistics import median, pstdev
from typing import Any


SUPPORTED_ANOMALY_METRICS = {
    "gmv", "order_count", "average_order_value", "refund_rate",
    "payment_conversion_rate", "gross_margin",
}


def detect_anomalies(
    rows: list[dict[str, Any]],
    metric: str,
    history: int = 8,
    z_threshold: float = 3.5,
    relative_threshold: float = 0.15,
) -> list[dict[str, Any]]:
    if metric not in SUPPORTED_ANOMALY_METRICS:
        raise ValueError(f"unsupported anomaly metric: {metric}")
    if history < 3:
        raise ValueError("history must be at least 3")
    if len(rows) <= history:
        return [{"metric": metric, "status": "insufficient_history", "required": history + 1, "actual": len(rows)}]
    results: list[dict[str, Any]] = []
    values = [float(row.get(metric) or 0) for row in rows]
    for index in range(history, len(rows)):
        baseline_values = values[index - history:index]
        baseline = median(baseline_values)
        deviations = [abs(value - baseline) for value in baseline_values]
        mad = median(deviations)
        current = values[index]
        absolute_change = current - baseline
        relative_change = absolute_change / abs(baseline) if baseline else (1.0 if current else 0.0)
        if mad:
            score = 0.6745 * absolute_change / mad
            algorithm = "rolling_median_mad"
        else:
            deviation = pstdev(baseline_values)
            score = absolute_change / deviation if deviation else relative_change
            algorithm = "stddev_fallback" if deviation else "relative_change_fallback"
        is_anomaly = abs(score) >= z_threshold or abs(relative_change) >= relative_threshold
        if not is_anomaly:
            continue
        impact = abs(absolute_change)
        severity_score = abs(score) + min(abs(relative_change), 2.0) + (1.0 if impact > abs(baseline) * 0.25 else 0.0)
        severity = "high" if severity_score >= 6 else "medium" if severity_score >= 3.5 else "low"
        results.append({
            "metric": metric,
            "status": "anomaly",
            "bucket": str(rows[index].get("bucket")),
            "current_value": current,
            "baseline_value": baseline,
            "absolute_change": absolute_change,
            "relative_change": relative_change,
            "anomaly_score": score,
            "direction": "increase" if absolute_change > 0 else "decrease",
            "severity": severity,
            "algorithm": algorithm,
            "thresholds": {"z_score": z_threshold, "relative_change": relative_threshold, "history": history},
            "data_complete": True,
        })
    return sorted(results, key=lambda row: (row["severity"] != "high", -abs(row["anomaly_score"])))
