"""Rule engine: runs a dataset's configured rules and scores each one."""
from __future__ import annotations

import logging
from dataclasses import dataclass, field

import pandas as pd

from .validators import REGISTRY, RuleOutcome

log = logging.getLogger(__name__)


@dataclass
class ValidationReport:
    results: list[dict] = field(default_factory=list)   # one dict per rule
    rejected: pd.Series | None = None                   # bool mask over rows
    reasons: pd.Series | None = None                    # "rule_a;rule_b" per row
    file_rejected: bool = False


def _rule_columns(rule: dict) -> list[str]:
    if "columns" in rule and rule["columns"]:
        return list(rule["columns"])
    return [rule["column"]] if "column" in rule else []


def validate(df: pd.DataFrame, rules: list[dict]) -> ValidationReport:
    report = ValidationReport()
    reject_flags: dict[str, pd.Series] = {}

    for rule in rules:
        rule_type = rule["type"]
        rule_id = rule.get("id") or f"{rule_type}:{','.join(_rule_columns(rule))}"
        severity = rule.get("severity", "error")
        if rule_type not in REGISTRY:
            raise ValueError(f"Unknown rule type {rule_type!r} in rule {rule_id!r}")

        columns = _rule_columns(rule)
        absent = [c for c in columns if c not in df.columns]
        if rule_type != "required_columns" and absent:
            outcome = RuleOutcome(pd.Series(True, index=df.index),
                                  f"column(s) not in file: {absent}")
        else:
            outcome = REGISTRY[rule_type](df, rule)

        failed = outcome.failed.fillna(False).astype(bool)
        rows_checked = len(df)
        rows_failed = int(failed.sum())
        failure_pct = round(100.0 * rows_failed / rows_checked, 4) if rows_checked else 0.0
        threshold = float(rule.get("max_failure_pct", 0))
        status = "PASS" if failure_pct <= threshold else "FAIL"

        report.results.append({
            "rule_id": rule_id,
            "rule_type": rule_type,
            "column_name": ",".join(columns) or None,
            "severity": severity,
            "status": status,
            "rows_checked": rows_checked,
            "rows_failed": rows_failed,
            "failure_pct": failure_pct,
            "threshold_pct": threshold,
            "details": outcome.details or None,
        })
        log.log(logging.INFO if status == "PASS" else logging.WARNING,
                "  [%s] %-34s failed=%d (%.2f%%) %s",
                status, rule_id, rows_failed, failure_pct, outcome.details)

        if severity == "error":
            reject_flags[rule_id] = failed
            if outcome.dataset_level and rows_failed:
                report.file_rejected = True
                log.error("  File rejected by dataset-level rule %s; remaining rules skipped",
                          rule_id)
                break

    flags = pd.DataFrame(reject_flags, index=df.index)
    if report.file_rejected:
        last_rule = report.results[-1]["rule_id"]
        report.rejected = pd.Series(True, index=df.index)
        report.reasons = pd.Series(last_rule, index=df.index)
    else:
        report.rejected = flags.any(axis=1) if len(flags.columns) else pd.Series(False, index=df.index)
        names = list(flags.columns)
        report.reasons = pd.Series(
            [";".join(n for n, hit in zip(names, row) if hit) for row in flags.to_numpy()],
            index=df.index, dtype=object)
    return report