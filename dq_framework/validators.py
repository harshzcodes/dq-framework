"""Reusable validation functions. Signature: validator(df, rule) -> RuleOutcome."""
from __future__ import annotations

from dataclasses import dataclass
from typing import Callable

import pandas as pd


@dataclass
class RuleOutcome:
    failed: pd.Series            # bool mask aligned to df.index, True = row failed
    details: str = ""            
    dataset_level: bool = False  # True = the rule is about the file, not single rows


Validator = Callable[[pd.DataFrame, dict], RuleOutcome]
REGISTRY: dict[str, Validator] = {}


def register(rule_type: str) -> Callable[[Validator], Validator]:
    def wrap(fn: Validator) -> Validator:
        REGISTRY[rule_type] = fn
        return fn
    return wrap


def _no_failures(df: pd.DataFrame) -> pd.Series:
    return pd.Series(False, index=df.index)


def _sample(values: pd.Series, n: int = 3) -> str:
    uniq = [str(v) for v in values.dropna().unique()[:n]]
    return ", ".join(repr(v) for v in uniq)

@register("required_columns")
def check_required_columns(df: pd.DataFrame, rule: dict) -> RuleOutcome:
    """All listed columns must exist in the file (catches schema drift)."""
    missing = [c for c in rule["columns"] if c not in df.columns]
    failed = pd.Series(bool(missing), index=df.index)
    details = f"missing columns: {missing}" if missing else ""
    return RuleOutcome(failed, details, dataset_level=True)


@register("not_null")
def check_not_null(df: pd.DataFrame, rule: dict) -> RuleOutcome:
    """Column must not contain missing values."""
    return RuleOutcome(df[rule["column"]].isna())


@register("unique")
def check_unique(df: pd.DataFrame, rule: dict) -> RuleOutcome:
    """Key columns must identify one record.

    Every row sharing a key with a different record is flagged, because we
    cannot tell which version is correct. Exact repeats of a whole row are
    left to no_duplicate_rows, and null keys to not_null.
    """
    cols = rule["columns"]
    exact_repeat = df.duplicated(keep="first")
    has_key = df[cols].notna().all(axis=1)
    candidates = df[~exact_repeat & has_key]
    clash = candidates.duplicated(subset=cols, keep=False)
    failed = _no_failures(df)
    failed.loc[clash[clash].index] = True
    return RuleOutcome(failed)


@register("no_duplicate_rows")
def check_no_duplicate_rows(df: pd.DataFrame, rule: dict) -> RuleOutcome:
    """Flags repeats of an identical row; the first occurrence is kept."""
    return RuleOutcome(df.duplicated(subset=rule.get("columns"), keep="first"))

@register("dtype")
def check_dtype(df: pd.DataFrame, rule: dict) -> RuleOutcome:
    """Non-null values must be castable to the expected type (integer|float)."""
    col, expected = rule["column"], rule["expected"]
    s = df[col]
    if expected == "integer":
        ok = s.astype("string").str.fullmatch(r"[+-]?\d+").fillna(False).astype(bool)
    elif expected == "float":
        ok = pd.to_numeric(s, errors="coerce").notna()
    else:
        raise ValueError(f"dtype rule: unsupported expected type {expected!r}")
    failed = s.notna() & ~ok
    return RuleOutcome(failed, f"e.g. {_sample(s[failed])}" if failed.any() else "")


@register("valid_date")
def check_valid_date(df: pd.DataFrame, rule: dict) -> RuleOutcome:
    """Non-null values must be real dates in `format`, within min/max bounds.

    max_date / min_date accept an ISO date or the keyword "today".
    """
    col = rule["column"]
    s = df[col]
    parsed = pd.to_datetime(s, format=rule.get("format", "%Y-%m-%d"), errors="coerce")
    failed = s.notna() & parsed.isna()

    def bound(value) -> pd.Timestamp:
        return pd.Timestamp.today().normalize() if value == "today" else pd.Timestamp(value)

    if "min_date" in rule:
        failed |= (parsed < bound(rule["min_date"])).fillna(False)
    if "max_date" in rule:
        failed |= (parsed > bound(rule["max_date"])).fillna(False)
    return RuleOutcome(failed, f"e.g. {_sample(s[failed])}" if failed.any() else "")


@register("numeric_range")
def check_numeric_range(df: pd.DataFrame, rule: dict) -> RuleOutcome:
    """Numeric values must sit within [min, max]. Use min: 0 to ban negatives.

    Values that are not numbers at all are ignored here; the dtype rule owns those.
    """
    s = df[rule["column"]]
    values = pd.to_numeric(s, errors="coerce")
    failed = _no_failures(df)
    if "min" in rule:
        failed |= (values < rule["min"]).fillna(False)
    if "max" in rule:
        failed |= (values > rule["max"]).fillna(False)
    return RuleOutcome(failed, f"e.g. {_sample(s[failed])}" if failed.any() else "")


@register("allowed_values")
def check_allowed_values(df: pd.DataFrame, rule: dict) -> RuleOutcome:
    """Non-null values must belong to the accepted set."""
    s = df[rule["column"]].astype("string")
    allowed = {str(v) for v in rule["values"]}
    if not rule.get("case_sensitive", False):
        s, allowed = s.str.lower(), {v.lower() for v in allowed}
    failed = s.notna() & ~s.isin(allowed).fillna(False).astype(bool)
    original = df[rule["column"]]
    return RuleOutcome(failed, f"unexpected: {_sample(original[failed])}" if failed.any() else "")


@register("regex")
def check_regex(df: pd.DataFrame, rule: dict) -> RuleOutcome:
    """Non-null values must fully match the regular expression."""
    s = df[rule["column"]]
    ok = s.astype("string").str.fullmatch(rule["pattern"]).fillna(False).astype(bool)
    failed = s.notna() & ~ok
    return RuleOutcome(failed, f"e.g. {_sample(s[failed])}" if failed.any() else "")