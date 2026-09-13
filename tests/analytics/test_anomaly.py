from shoppulse.analytics.anomaly import detect_anomalies


def rows(values):
    return [{"bucket": index, "gmv": value} for index, value in enumerate(values)]


def test_detects_direction_and_robust_baseline():
    result = detect_anomalies(rows([100, 101, 99, 100, 102, 98, 101, 99, 50]), "gmv", history=8)
    assert len(result) == 1
    assert result[0]["direction"] == "decrease"
    assert result[0]["baseline_value"] == 100


def test_reports_insufficient_history_instead_of_guessing():
    result = detect_anomalies(rows([1, 2, 3]), "gmv", history=8)
    assert result == [{"metric": "gmv", "status": "insufficient_history", "required": 9, "actual": 3}]


def test_stable_series_has_no_anomaly():
    assert detect_anomalies(rows([100] * 12), "gmv", history=8) == []
