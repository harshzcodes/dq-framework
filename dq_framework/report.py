"""Data quality summary report (Markdown for people, JSON for machines)."""
from __future__ import annotations

import json
from pathlib import Path


def _pct(part: int, whole: int) -> str:
    return f"{100.0 * part / whole:.2f}%" if whole else "n/a"


def _table(headers: list[str], rows: list[list]) -> str:
    lines = ["| " + " | ".join(headers) + " |", "|" + "|".join("---" for _ in headers) + "|"]
    lines += ["| " + " | ".join(str(c) for c in row) + " |" for row in rows]
    return "\n".join(lines)


def write_report(run: dict, files: list[dict], results: list[dict], out_dir: Path) -> Path:
    out_dir.mkdir(parents=True, exist_ok=True)
    failed = sorted((r for r in results if r["status"] == "FAIL"),
                    key=lambda r: r["rows_failed"], reverse=True)

    md = [
        f"# Data Quality Report: {run['run_id']}",
        "",
        f"- Started (UTC): {run['started_at']}",
        f"- Finished (UTC): {run['finished_at']}",
        f"- Input: `{run['input_dir']}`",
        f"- Database: `{run['database']}` ({run['backend']})",
        "",
        "## Summary",
        "",
        _table(["Metric", "Value"], [
            ["Files processed", run["files_processed"]],
            ["Records processed", run["rows_processed"]],
            ["Valid records loaded", run["rows_valid"]],
            ["Rejected records", f"{run['rows_rejected']} "
                                 f"({_pct(run['rows_rejected'], run['rows_processed'])})"],
            ["Validation rules run", run["rules_run"]],
            ["Validation rules failed", f"{run['rules_failed']} "
                                        f"({_pct(run['rules_failed'], run['rules_run'])})"],
        ]),
        "",
        "## Files",
        "",
        _table(["Dataset", "File", "Status", "Processed", "Valid", "Rejected", "Reject %",
                "Rules failed"],
               [[f["dataset"], f["source_file"], f["file_status"], f["rows_processed"],
                 f["rows_valid"], f["rows_rejected"],
                 _pct(f["rows_rejected"], f["rows_processed"]),
                 f"{f['rules_failed']}/{f['rules_run']}"] for f in files]),
        "",
        "## Failed validation rules",
        "",
        _table(["Dataset", "File", "Rule", "Type", "Severity", "Rows failed", "Failure %",
                "Details"],
               [[r["dataset"], r["source_file"], r["rule_id"], r["rule_type"], r["severity"],
                 r["rows_failed"], f"{r['failure_pct']:.2f}%", r["details"] or ""]
                for r in failed]) if failed else "All rules passed.",
        "",
        "## All validation results",
        "",
        _table(["Dataset", "File", "Rule", "Status", "Rows failed", "Failure %"],
               [[r["dataset"], r["source_file"], r["rule_id"], r["status"], r["rows_failed"],
                 f"{r['failure_pct']:.2f}%"] for r in results]),
        "",
    ]
    md_path = out_dir / f"dq_report_{run['run_id']}.md"
    md_path.write_text("\n".join(md), encoding="utf-8")
    (out_dir / f"dq_report_{run['run_id']}.json").write_text(
        json.dumps({"run": run, "files": files, "results": results}, indent=2, default=str),
        encoding="utf-8")
    return md_path