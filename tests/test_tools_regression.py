from tools import database


def test_order_status_uses_bound_parameter(monkeypatch):
    captured = {}

    def fake_query(statement, parameters):
        captured.update(statement=statement, parameters=parameters)
        return [{"order_no": "SO-1", "ordered_at": "2026-01-01", "status": "completed", "shipped_at": None, "completed_at": None}]

    monkeypatch.setattr(database, "query_rows", fake_query)
    output = database.get_order_status.invoke({"order_id": "SO-1' OR 1=1 --"})
    assert ":order_no" in captured["statement"]
    assert "OR 1=1" not in captured["statement"]
    assert captured["parameters"]["order_no"] == "SO-1' OR 1=1 --"
    assert "completed" in output


def test_customer_lookup_is_parameterized(monkeypatch):
    captured = {}

    def fake_query(statement, parameters):
        captured.update(statement=statement, parameters=parameters)
        return []

    monkeypatch.setattr(database, "query_rows", fake_query)
    assert database.find_customer_by_email("x'@example.test") is None
    assert captured["parameters"] == {"email": "x'@example.test"}
