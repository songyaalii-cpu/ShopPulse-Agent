"""Deterministic, correlated e-commerce dataset generator.

The generator is pure: it returns rows and never connects to a database. This makes
the seed contract easy to test and keeps destructive database operations in the CLI.
"""

import hashlib
import json
import random
from dataclasses import dataclass
from datetime import UTC, date, datetime, timedelta
from decimal import Decimal, ROUND_HALF_UP
from typing import Any

CENT = Decimal("0.01")
CHANNELS = ("web", "app", "marketplace", "social")
REGIONS = ("East", "South", "North", "West")
CATEGORIES = ("Electronics", "Home", "Beauty", "Apparel", "Sports")


def cash(value: float | Decimal) -> Decimal:
    return Decimal(str(value)).quantize(CENT, rounding=ROUND_HALF_UP)


@dataclass(frozen=True)
class GenerationConfig:
    customers: int = 2_000
    products: int = 200
    orders: int = 20_000
    campaigns: int = 30
    events: int = 200_000
    months: int = 12
    seed: int = 20260804
    end_date: date = date(2026, 7, 31)

    def validate(self) -> None:
        if min(self.customers, self.products, self.orders, self.campaigns, self.events, self.months) < 1:
            raise ValueError("All generation sizes must be positive")
        if self.events < self.orders * 5:
            raise ValueError("events must be at least five per order to preserve the funnel")


def _weighted_index(rng: random.Random, size: int, high_value_share: float = 0.2) -> int:
    # The leading 20% receives approximately 55% of orders (repeat-purchase behavior).
    high = max(1, int(size * high_value_share))
    if high >= size:
        return rng.randrange(size)
    return rng.randrange(high) if rng.random() < 0.55 else rng.randrange(high, size)


def _season_factor(day: date, campaigns: list[dict[str, Any]]) -> float:
    factor = 1.25 if day.weekday() >= 5 else 1.0
    if (day.month, day.day) in {(1, 1), (5, 1), (6, 18), (10, 1), (11, 11), (12, 12)}:
        factor *= 1.8
    at = datetime.combine(day, datetime.min.time(), UTC)
    if any(c["start_at"] <= at <= c["end_at"] for c in campaigns):
        factor *= 1.55
    return factor


def build_dataset(config: GenerationConfig) -> dict[str, list[dict[str, Any]]]:
    config.validate()
    rng = random.Random(config.seed)
    start_date = config.end_date - timedelta(days=365)
    now = datetime.combine(config.end_date + timedelta(days=1), datetime.min.time(), UTC)

    provinces = {
        "East": ("Shanghai", "Zhejiang"), "South": ("Guangdong", "Fujian"),
        "North": ("Beijing", "Hebei"), "West": ("Sichuan", "Chongqing"),
    }
    customers: list[dict[str, Any]] = []
    for i in range(1, config.customers + 1):
        region = rng.choices(REGIONS, weights=(30, 28, 24, 18))[0]
        province = rng.choice(provinces[region])
        registered = datetime.combine(start_date - timedelta(days=rng.randint(1, 730)), datetime.min.time(), UTC)
        customers.append({
            "id": i, "customer_code": f"CUS-{i:06d}", "name": f"Customer {i:06d}",
            "email": f"customer{i:06d}@example.test", "phone": f"1{rng.randint(3000000000, 9999999999)}",
            "gender": rng.choices(("female", "male", "other", "unknown"), (48, 48, 1, 3))[0],
            "birth_date": date(rng.randint(1960, 2003), rng.randint(1, 12), rng.randint(1, 28)),
            "segment": "high_value" if i <= max(1, int(config.customers * 0.2)) else rng.choice(("standard", "growth", "new")),
            "region": region, "province": province, "city": f"{province} City",
            "registration_channel": rng.choices(CHANNELS, (40, 35, 15, 10))[0], "registered_at": registered,
        })

    products: list[dict[str, Any]] = []
    for i in range(1, config.products + 1):
        category = CATEGORIES[(i - 1) % len(CATEGORIES)]
        base = {"Electronics": 900, "Home": 260, "Beauty": 120, "Apparel": 180, "Sports": 320}[category]
        list_price = cash(base * rng.uniform(0.55, 1.8))
        sale_price = cash(list_price * Decimal(str(rng.uniform(0.82, 0.98))))
        unit_cost = cash(sale_price * Decimal(str(rng.uniform(0.48, 0.72))))
        products.append({
            "id": i, "sku": f"SP-{i:05d}", "name": f"{category} Product {i:03d}",
            "category": category, "subcategory": f"{category}-{(i % 4) + 1}",
            "brand": f"Brand-{(i % 12) + 1:02d}", "list_price": list_price,
            "sale_price": sale_price, "unit_cost": unit_cost, "status": "active",
            "launched_at": datetime.combine(start_date - timedelta(days=rng.randint(30, 700)), datetime.min.time(), UTC),
        })

    campaigns: list[dict[str, Any]] = []
    for i in range(1, config.campaigns + 1):
        campaign_day = start_date + timedelta(days=int((i - 1) * 365 / config.campaigns))
        duration = rng.randint(4, 12)
        campaigns.append({
            "id": i, "campaign_code": f"CAM-{i:04d}", "name": f"Campaign {i:02d}",
            "campaign_type": rng.choice(("discount", "traffic", "retention", "launch")),
            "channel": rng.choice(CHANNELS), "budget": cash(rng.uniform(20_000, 300_000)),
            "start_at": datetime.combine(campaign_day, datetime.min.time(), UTC),
            "end_at": datetime.combine(campaign_day + timedelta(days=duration), datetime.max.time(), UTC),
            "status": "completed" if campaign_day + timedelta(days=duration) <= config.end_date else "active",
        })

    days = [start_date + timedelta(days=i) for i in range(366)]
    day_weights = [_season_factor(day, campaigns) for day in days]
    orders: list[dict[str, Any]] = []
    items: list[dict[str, Any]] = []
    order_products: dict[int, list[int]] = {}
    item_id = 1
    for order_id in range(1, config.orders + 1):
        customer_index = _weighted_index(rng, config.customers)
        customer = customers[customer_index]
        order_day = rng.choices(days, weights=day_weights)[0]
        channel = rng.choices(CHANNELS, weights=(38, 35, 18, 9))[0]
        active_campaigns = [c for c in campaigns if c["channel"] == channel and c["start_at"].date() <= order_day <= c["end_at"].date()]
        campaign = rng.choice(active_campaigns) if active_campaigns and rng.random() < 0.68 else None
        ordered_at = datetime.combine(order_day, datetime.min.time(), UTC) + timedelta(seconds=rng.randint(8 * 3600, 23 * 3600))
        status = rng.choices(("completed", "shipped", "paid", "pending", "cancelled"), (88, 5, 3, 2, 2))[0]
        product_count = rng.choices((2, 3, 4), (45, 40, 15))[0]
        chosen = rng.sample(range(config.products), k=min(product_count, config.products)) if status != "cancelled" else []
        order_products[order_id] = [index + 1 for index in chosen]
        gross = Decimal(0)
        discount = Decimal(0)
        for product_index in chosen:
            product = products[product_index]
            quantity = rng.choices((1, 2, 3), (82, 15, 3))[0]
            unit_price = product["sale_price"]
            discount_rate = Decimal(str(rng.uniform(0.03, 0.12))) if campaign else Decimal(0)
            item_discount = cash(unit_price * quantity * discount_rate)
            line_amount = cash(unit_price * quantity - item_discount)
            gross += unit_price * quantity
            discount += item_discount
            items.append({
                "id": item_id, "order_id": order_id, "product_id": product["id"], "quantity": quantity,
                "unit_price": unit_price, "unit_cost": product["unit_cost"],
                "discount_amount": item_discount, "line_amount": line_amount,
            })
            item_id += 1
        shipping = Decimal(0) if gross >= 299 or status == "cancelled" else cash(12)
        paid = cash(gross - discount + shipping)
        paid_at = ordered_at + timedelta(minutes=rng.randint(1, 35)) if status not in {"pending", "cancelled"} else None
        shipped_at = paid_at + timedelta(hours=rng.randint(8, 72)) if status in {"shipped", "completed"} else None
        completed_at = shipped_at + timedelta(days=rng.randint(1, 6)) if status == "completed" else None
        orders.append({
            "id": order_id, "order_no": f"SO-{order_day:%Y%m%d}-{order_id:06d}",
            "customer_id": customer["id"], "campaign_id": campaign["id"] if campaign else None,
            "channel": channel, "status": status, "region": customer["region"],
            "order_amount": cash(gross), "discount_amount": cash(discount), "shipping_fee": shipping,
            "paid_amount": paid, "ordered_at": ordered_at, "paid_at": paid_at,
            "shipped_at": shipped_at, "completed_at": completed_at,
        })

    refunds: list[dict[str, Any]] = []
    refundable = [order for order in orders if order["status"] == "completed" and order_products[order["id"]]]
    refund_target = min(len(refundable), max(1, int(config.orders * 0.13)))
    refund_weights = []
    for order in refundable:
        categories = [products[pid - 1]["category"] for pid in order_products[order["id"]]]
        weight = 1.7 if "Apparel" in categories else 1.0
        # Explainable anomaly: South-region refunds rise in the final 60 days.
        if order["region"] == "South" and order["ordered_at"].date() >= config.end_date - timedelta(days=60):
            weight *= 3.5
        refund_weights.append(weight)
    selected_indices: set[int] = set()
    while len(selected_indices) < refund_target:
        selected_indices.add(rng.choices(range(len(refundable)), weights=refund_weights)[0])
    item_by_order: dict[int, list[dict[str, Any]]] = {order_id: [] for order_id in order_products}
    for item in items:
        item_by_order[item["order_id"]].append(item)
    for refund_id, selected in enumerate(sorted(selected_indices), 1):
        order = refundable[selected]
        item = rng.choice(item_by_order[order["id"]])
        full = rng.random() < 0.28
        amount = min(order["paid_amount"], order["paid_amount"] if full else item["line_amount"])
        requested = order["completed_at"] + timedelta(days=rng.randint(1, 20))
        refunds.append({
            "id": refund_id, "refund_no": f"RF-{refund_id:06d}", "order_id": order["id"],
            "order_item_id": None if full else item["id"], "customer_id": order["customer_id"],
            "reason": rng.choices(("size_issue", "logistics_delay", "quality_issue", "changed_mind"), (28, 24, 30, 18))[0],
            "refund_type": "full" if full else "partial", "status": "completed",
            "refund_amount": cash(amount), "requested_at": requested,
            "completed_at": requested + timedelta(days=rng.randint(1, 5)),
        })

    inventory: list[dict[str, Any]] = []
    inventory_id = 1
    sold_totals = {product["id"]: 0 for product in products}
    for item in items:
        sold_totals[item["product_id"]] += item["quantity"]
    for month in range(config.months + 1):
        snapshot_day = config.end_date - timedelta(days=30 * (config.months - month))
        for product in products:
            for warehouse in ("WH-EAST", "WH-WEST"):
                sold = int(sold_totals[product["id"]] * month / max(config.months, 1))
                available = max(0, 480 + (product["id"] % 17) * 12 - sold // 2 + month * 35)
                # Explainable anomaly: SP-00007 is stocked out in the last two snapshots.
                if product["id"] == 7 and month >= config.months - 1:
                    available = 0
                inventory.append({
                    "id": inventory_id, "product_id": product["id"], "warehouse_code": warehouse,
                    "available_quantity": available, "reserved_quantity": min(25, sold % 26),
                    "inbound_quantity": 120 if available < 80 else 0, "snapshot_date": snapshot_day,
                })
                inventory_id += 1

    events: list[dict[str, Any]] = []
    event_id = 1
    for order in orders:
        if order["status"] == "cancelled" or not order_products[order["id"]]:
            continue
        product_id = order_products[order["id"]][0]
        session = f"SES-O-{order['id']:07d}"
        base = order["ordered_at"] - timedelta(minutes=rng.randint(15, 90))
        types = ("view", "click", "add_to_cart", "checkout", "purchase")
        for offset, event_type in enumerate(types):
            occurred = base + timedelta(minutes=offset * 3)
            events.append({
                "id": event_id, "event_id": f"EVT-{event_id:09d}", "customer_id": order["customer_id"],
                "session_id": session, "product_id": product_id, "campaign_id": order["campaign_id"],
                "event_type": event_type, "channel": order["channel"],
                "device_type": "mobile" if order["channel"] in {"app", "social"} else "desktop",
                "occurred_at": occurred, "properties": {"source": "order_funnel", "order_no": order["order_no"]},
            })
            event_id += 1
    abandoned = 1
    while len(events) < config.events:
        day = rng.choice(days)
        channel = rng.choices(CHANNELS, (34, 34, 17, 15))[0]
        customer = customers[rng.randrange(config.customers)] if rng.random() < 0.72 else None
        session = f"SES-A-{abandoned:08d}"
        base = datetime.combine(day, datetime.min.time(), UTC) + timedelta(seconds=rng.randint(0, 86300))
        # Explainable anomaly: social conversion drops in the final 45 days.
        max_stage = rng.choices((1, 2, 3, 4), (38, 32, 22, 8))[0]
        if channel == "social" and day >= config.end_date - timedelta(days=45):
            max_stage = min(max_stage, 2)
        for offset, event_type in enumerate(("view", "click", "add_to_cart", "checkout")[:max_stage]):
            if len(events) >= config.events:
                break
            events.append({
                "id": event_id, "event_id": f"EVT-{event_id:09d}",
                "customer_id": customer["id"] if customer else None, "session_id": session,
                "product_id": rng.randint(1, config.products), "campaign_id": None,
                "event_type": event_type, "channel": channel,
                "device_type": "mobile" if channel in {"app", "social"} else "desktop",
                "occurred_at": base + timedelta(minutes=offset * 2), "properties": {"source": "browse_session"},
            })
            event_id += 1
        abandoned += 1

    return {
        "customers": customers, "products": products, "marketing_campaigns": campaigns,
        "orders": orders, "order_items": items, "refunds": refunds,
        "inventory_snapshots": inventory, "user_events": events,
    }


def dataset_fingerprint(dataset: dict[str, list[dict[str, Any]]]) -> str:
    """Stable digest used by deterministic-generation regression tests."""
    payload = json.dumps(dataset, sort_keys=True, default=str, separators=(",", ":"))
    return hashlib.sha256(payload.encode()).hexdigest()
