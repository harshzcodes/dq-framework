import pandas as pd

from dq_framework.engine import validate
from dq_framework.validators import REGISTRY


def frame():
    return pd.DataFrame({
        "id":    ["1", "2", "2", "3", "3", None],
        "qty":   ["5", "-1", "-1", "abc", "2", "1"],
        "day":   ["2026-01-05", "2026-02-30", "2026-02-30", "2026-01-07", "2031-01-01", None],
        "pay":   ["Card", "card", "card", "Bitcoin", "Cash", None],
    })


def failed(rule):
    return REGISTRY[rule["type"]](frame(), rule).failed.tolist()


def test_required_columns():
    out = REGISTRY["required_columns"](frame(), {"columns": ["id", "price"]})
    assert out.failed.all() and out.dataset_level and "price" in out.details


def test_not_null():
    assert failed({"type": "not_null", "column": "id"}) == [False] * 5 + [True]


def test_duplicate_rows_keeps_first():
    assert failed({"type": "no_duplicate_rows"}) == [False, False, True, False, False, False]


def test_unique_flags_conflicts_but_not_exact_repeats_or_nulls():
    assert failed({"type": "unique", "columns": ["id"]}) == [False, False, False, True, True, False]


def test_dtype_integer():
    assert failed({"type": "dtype", "column": "qty", "expected": "integer"}) == \
        [False, False, False, True, False, False]


def test_valid_date_catches_impossible_and_future_dates():
    rule = {"type": "valid_date", "column": "day", "max_date": "2026-12-31"}
    assert failed(rule) == [False, True, True, False, True, False]


def test_numeric_range_ignores_non_numbers():
    assert failed({"type": "numeric_range", "column": "qty", "min": 0}) == \
        [False, True, True, False, False, False]


def test_allowed_values_case_insensitive_by_default():
    rule = {"type": "allowed_values", "column": "pay", "values": ["Card", "Cash"]}
    assert failed(rule) == [False, False, False, True, False, False]


def test_engine_status_severity_and_reasons():
    rules = [
        {"id": "qty_ok", "type": "numeric_range", "column": "qty", "min": 0},
        {"id": "pay_ok", "type": "allowed_values", "column": "pay", "values": ["Card", "Cash"],
         "severity": "warn", "max_failure_pct": 50},
    ]
    rep = validate(frame(), rules)
    assert [r["status"] for r in rep.results] == ["FAIL", "PASS"]
    assert rep.rejected.tolist() == [False, True, True, False, False, False]  # warn never rejects
    assert rep.reasons[1] == "qty_ok"


def test_engine_rejects_whole_file_on_missing_mandatory_column():
    rules = [{"id": "cols", "type": "required_columns", "columns": ["price"]},
             {"id": "never_run", "type": "not_null", "column": "id"}]
    rep = validate(frame(), rules)
    assert rep.file_rejected and rep.rejected.all() and len(rep.results) == 1
