from collections import defaultdict
from decimal import Decimal

from shoppulse.data.generator import GenerationConfig, build_dataset, dataset_fingerprint


def small_config(seed=11):
    return GenerationConfig(customers=40, products=15, orders=120, campaigns=4, events=700, months=3, seed=seed)


def test_generation_is_deterministic():
    first = build_dataset(small_config())
    second = build_dataset(small_config())
    different = build_dataset(small_config(seed=12))
    assert dataset_fingerprint(first) == dataset_fingerprint(second)
    assert dataset_fingerprint(first) != dataset_fingerprint(different)


def test_amounts_refunds_and_foreign_keys_are_consistent():
    data = build_dataset(small_config())
    customers = {row["id"] for row in data["customers"]}
    products = {row["id"] for row in data["products"]}
    items_by_order = defaultdict(list)
    for item in data["order_items"]:
        assert item["product_id"] in products
        assert item["line_amount"] == item["quantity"] * item["unit_price"] - item["discount_amount"]
        items_by_order[item["order_id"]].append(item)
    paid_by_order = {}
    for order in data["orders"]:
        assert order["customer_id"] in customers
        order_items = items_by_order[order["id"]]
        assert order["order_amount"] == sum((i["quantity"] * i["unit_price"] for i in order_items), Decimal(0))
        assert order["discount_amount"] == sum((i["discount_amount"] for i in order_items), Decimal(0))
        assert order["paid_amount"] == order["order_amount"] - order["discount_amount"] + order["shipping_fee"]
        paid_by_order[order["id"]] = order["paid_amount"]
    refunds = defaultdict(Decimal)
    for refund in data["refunds"]:
        refunds[refund["order_id"]] += refund["refund_amount"]
    assert all(amount <= paid_by_order[order_id] for order_id, amount in refunds.items())


def test_behavior_event_sequence_and_scale():
    data = build_dataset(small_config())
    assert len(data["user_events"]) == 700
    stages = {"view": 0, "click": 1, "add_to_cart": 2, "checkout": 3, "purchase": 4}
    sessions = defaultdict(list)
    for event in data["user_events"]:
        sessions[event["session_id"]].append(event)
    for events in sessions.values():
        ordered = sorted(events, key=lambda event: event["occurred_at"])
        assert [stages[event["event_type"]] for event in ordered] == sorted(stages[event["event_type"]] for event in ordered)


def test_realistic_correlations_and_documented_anomalies_exist():
    data = build_dataset(small_config())
    high = {customer["id"] for customer in data["customers"] if customer["segment"] == "high_value"}
    high_orders = sum(order["customer_id"] in high for order in data["orders"])
    assert high_orders / len(data["orders"]) > 0.35
    sku7 = [row for row in data["inventory_snapshots"] if row["product_id"] == 7]
    assert any(row["available_quantity"] == 0 for row in sku7)
