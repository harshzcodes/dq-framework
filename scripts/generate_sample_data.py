"""Generate sample retail CSVs with intentionally injected data quality problems.

Two batches are produced so pipeline runs can be compared:
  data/raw/batch_1  -> a "bad day": many problems + one file missing a mandatory column
  data/raw/batch_2  -> a "better day": the same feeds after upstream fixes, few problems

The schema mirrors common public retail datasets (order line, customer, product,
price, quantity, country). Deterministic: the same seed always yields the same files.
"""
from __future__ import annotations

import csv
import random
from datetime import date, timedelta
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1] / "data" / "raw"

CATEGORIES = ["Electronics", "Home", "Clothing", "Toys", "Grocery"]
PAYMENTS = ["Card", "Cash", "PayPal", "Gift Card"]
COUNTRIES = ["United States", "Canada", "United Kingdom", "Germany", "India"]
SEGMENTS = ["Consumer", "Corporate", "Small Business"]
FIRST = ["Ava", "Liam", "Noah", "Mia", "Ethan", "Zoe", "Ravi", "Sara", "Omar", "Lena"]
LAST = ["Smith", "Patel", "Garcia", "Kim", "Brown", "Nguyen", "Müller", "Jones"]

SALES_COLS = ["order_id", "order_date", "customer_id", "product_id", "category",
              "quantity", "unit_price", "payment_method", "country"]
CUSTOMER_COLS = ["customer_id", "customer_name", "email", "signup_date", "country", "segment"]


def make_customers(rng: random.Random, n: int) -> list[dict]:
    rows = []
    for i in range(1, n + 1):
        first, last = rng.choice(FIRST), rng.choice(LAST)
        rows.append({
            "customer_id": f"C{i:04d}",
            "customer_name": f"{first} {last}",
            "email": f"{first}.{last}{i}@example.com".lower().replace("ü", "u"),
            "signup_date": (date(2024, 1, 1) + timedelta(days=rng.randrange(700))).isoformat(),
            "country": rng.choice(COUNTRIES),
            "segment": rng.choice(SEGMENTS),
        })
    return rows


def make_sales(rng: random.Random, n: int, start_id: int, month: int, n_customers: int) -> list[dict]:
    rows = []
    for i in range(n):
        rows.append({
            "order_id": f"ORD{start_id + i:06d}",
            "order_date": (date(2026, month, 1) + timedelta(days=rng.randrange(28))).isoformat(),
            "customer_id": f"C{rng.randint(1, n_customers):04d}",
            "product_id": f"P{rng.randint(1, 60):03d}",
            "category": rng.choice(CATEGORIES),
            "quantity": str(rng.randint(1, 8)),
            "unit_price": f"{rng.uniform(2, 400):.2f}",
            "payment_method": rng.choice(PAYMENTS),
            "country": rng.choice(COUNTRIES),
        })
    return rows


def corrupt_sales(rng: random.Random, rows: list[dict], plan: dict[str, int]) -> list[dict]:
    """Apply each problem to its own distinct rows so counts stay easy to verify."""
    idx = list(range(len(rows)))
    rng.shuffle(idx)
    take = lambda k: [idx.pop() for _ in range(plan.get(k, 0))]

    for i in take("missing_customer_id"):
        rows[i]["customer_id"] = ""
    for i in take("missing_order_date"):
        rows[i]["order_date"] = rng.choice(["", "NULL"])
    for i in take("bad_quantity_type"):
        rows[i]["quantity"] = rng.choice(["abc", "ten", "3.5"])
    for i in take("invalid_date"):
        rows[i]["order_date"] = rng.choice(["2026-02-30", "2026-13-01", "15/01/2026", "not_a_date"])
    for i in take("future_date"):
        rows[i]["order_date"] = "2031-01-15"
    for i in take("negative_quantity"):
        rows[i]["quantity"] = str(-rng.randint(1, 5))
    for i in take("negative_price"):
        rows[i]["unit_price"] = f"-{rng.uniform(1, 50):.2f}"
    for i in take("bad_payment_method"):
        rows[i]["payment_method"] = rng.choice(["Bitcoin", "Cheque", "UNKNOWN"])
    for i in take("bad_category"):
        rows[i]["category"] = rng.choice(["Misc??", "TBD"])
    for i in take("unknown_country"):
        rows[i]["country"] = rng.choice(["Atlantis", "N. America"])

    extra = []
    for i in take("exact_duplicate"):                 # same row delivered twice
        extra.append(dict(rows[i]))
    for i in take("pk_conflict"):                     # same order_id, different content
        clash = dict(rows[i])
        clash["quantity"] = str(int(clash["quantity"]) + 1)
        extra.append(clash)
    return rows + extra


def corrupt_customers(rng: random.Random, rows: list[dict], plan: dict[str, int]) -> list[dict]:
    idx = list(range(len(rows)))
    rng.shuffle(idx)
    take = lambda k: [idx.pop() for _ in range(plan.get(k, 0))]

    for i in take("missing_email"):
        rows[i]["email"] = ""
    for i in take("bad_email"):
        rows[i]["email"] = rng.choice(["not-an-email", "user@", "@example.com"])
    for i in take("invalid_signup_date"):
        rows[i]["signup_date"] = rng.choice(["2025-02-31", "01-15-2025"])
    for i in take("bad_segment"):
        rows[i]["segment"] = rng.choice(["VIP", "consumer?"])
    extra = []
    for i in take("exact_duplicate"):
        extra.append(dict(rows[i]))
    for i in take("pk_conflict"):
        clash = dict(rows[i])
        clash["customer_name"] += " Jr"
        extra.append(clash)
    return rows + extra


def write(path: Path, cols: list[str], rows: list[dict]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", newline="", encoding="utf-8") as fh:
        w = csv.DictWriter(fh, fieldnames=cols, extrasaction="ignore")
        w.writeheader()
        w.writerows(rows)
    print(f"wrote {path.relative_to(ROOT.parents[1])}  ({len(rows)} rows)")


def main() -> None:
    rng = random.Random(42)

    # ---- batch 1: bad day -------------------------------------------------
    b1 = ROOT / "batch_1"
    customers = corrupt_customers(rng, make_customers(rng, 100), {
        "missing_email": 4, "bad_email": 6, "invalid_signup_date": 3,
        "bad_segment": 4, "exact_duplicate": 2, "pk_conflict": 3})
    write(b1 / "customers.csv", CUSTOMER_COLS, customers)

    sales = corrupt_sales(rng, make_sales(rng, 500, 1, 1, 100), {
        "missing_customer_id": 12, "missing_order_date": 5, "bad_quantity_type": 6,
        "invalid_date": 7, "future_date": 3, "negative_quantity": 9, "negative_price": 6,
        "bad_payment_method": 10, "bad_category": 6, "unknown_country": 5,
        "exact_duplicate": 8, "pk_conflict": 4})
    write(b1 / "sales_2026_01_store_a.csv", SALES_COLS, sales)

    # A second, smaller file for the same dataset (multi-file support)
    sales_b = corrupt_sales(rng, make_sales(rng, 200, 501, 1, 100), {
        "missing_customer_id": 3, "negative_price": 2, "exact_duplicate": 2})
    write(b1 / "sales_2026_01_store_b.csv", SALES_COLS, sales_b)

    # A file whose schema drifted: mandatory column unit_price is missing
    legacy = make_sales(rng, 50, 701, 1, 100)
    write(b1 / "sales_2026_01_legacy_export.csv",
          [c for c in SALES_COLS if c != "unit_price"], legacy)

    # ---- batch 2: better day ----------------------------------------------
    b2 = ROOT / "batch_2"
    customers2 = corrupt_customers(rng, make_customers(rng, 100), {"bad_email": 1, "bad_segment": 1})
    write(b2 / "customers.csv", CUSTOMER_COLS, customers2)
    sales2 = corrupt_sales(rng, make_sales(rng, 600, 1001, 2, 100), {
        "missing_customer_id": 2, "invalid_date": 1, "negative_quantity": 2,
        "bad_payment_method": 3, "exact_duplicate": 1})
    write(b2 / "sales_2026_02_store_a.csv", SALES_COLS, sales2)


if __name__ == "__main__":
    main()
