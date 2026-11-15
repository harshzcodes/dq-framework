"""Pipeline orchestration: ingest -> validate -> split -> load -> report."""
from __future__ import annotations

import json
import logging
import time
import uuid
from datetime import datetime, timezone
from pathlib import Path

import yaml

from .engine import validate
from .ingestion import discover_files, read_csv
from .report import write_report
from .storage import Warehouse

log = logging.getLogger("dq_framework")


def _now() -> datetime:
    """Current UTC time, naive, second precision (portable across DB engines)."""
    return datetime.now(timezone.utc).replace(tzinfo=None, microsecond=0)


def setup_logging(log_dir: Path, run_id: str) -> Path:
    log_dir.mkdir(parents=True, exist_ok=True)
    log_file = log_dir / f"{run_id}.log"
    fmt = logging.Formatter("%(asctime)s | %(levelname)-7s | %(name)s | %(message)s")
    fmt.converter = time.gmtime   # log in UTC, same clock as run_id and the tables
    root = logging.getLogger()
    root.setLevel(logging.INFO)
    for handler in list(root.handlers):
        root.removeHandler(handler)
    for handler in (logging.StreamHandler(), logging.FileHandler(log_file, encoding="utf-8")):
        handler.setFormatter(fmt)
        root.addHandler(handler)
    return log_file


def load_config(path: str | Path) -> dict:
    with open(path, encoding="utf-8") as fh:
        return yaml.safe_load(fh)


def run_pipeline(input_dir: str | Path, config_path: str | Path = "config/rules.yaml",
                 db_path: str | Path = "warehouse/dq.duckdb",
                 output_dir: str | Path = "output", backend: str = "auto") -> dict:
    input_dir, output_dir = Path(input_dir), Path(output_dir)
    started = _now()
    run_id = f"run_{started:%Y%m%dT%H%M%S}_{uuid.uuid4().hex[:6]}"
    log_file = setup_logging(output_dir / "logs", run_id)
    log.info("Pipeline run %s started | input=%s", run_id, input_dir)

    config = load_config(config_path)
    warehouse = Warehouse(db_path, backend)
    reject_dir = output_dir / "rejected" / run_id
    file_summaries: list[dict] = []
    all_results: list[dict] = []

    for dataset, spec in config["datasets"].items():
        files = discover_files(input_dir, spec["file_pattern"])
        if not files:
            log.warning("Dataset %s: no files match %s", dataset, spec["file_pattern"])
        for path in files:
            file_started = _now()
            log.info("Dataset %s | file %s", dataset, path.name)
            df = read_csv(path)
            report = validate(df, spec["rules"])

            executed_at = _now()
            for result in report.results:
                all_results.append({"run_id": run_id, "dataset": dataset,
                                    "source_file": path.name, **result,
                                    "executed_at": executed_at})

            valid = df[~report.rejected]
            rejected = df[report.rejected]

            # Valid records -> analytical table
            if len(valid):
                warehouse.load_clean(
                    spec["target_table"], valid, spec["schema"],
                    spec.get("primary_key", []), spec.get("date_format", "%Y-%m-%d"),
                    {"_run_id": run_id, "_source_file": path.name, "_loaded_at": _now()})

            # Rejected records -> quarantine file + table, with the reason
            if len(rejected):
                reject_dir.mkdir(parents=True, exist_ok=True)
                out = rejected.copy()
                out.insert(0, "_row_number", out.index + 2)   # line number in the CSV
                out.insert(1, "_reject_reasons", report.reasons[report.rejected])
                out.insert(2, "_run_id", run_id)
                out.to_csv(reject_dir / f"{dataset}__{path.stem}__rejected.csv", index=False)
                rejected_at = _now()
                warehouse.insert_records("dq_rejected_records", [
                    {"run_id": run_id, "dataset": dataset, "source_file": path.name,
                     "row_number": int(idx) + 2, "reject_reasons": report.reasons[idx],
                     "record_json": json.dumps(
                         {k: (None if v is None or v != v else v) for k, v in row.items()},
                         ensure_ascii=False),
                     "rejected_at": rejected_at}
                    for idx, row in rejected.iterrows()])

            status = ("REJECTED" if report.file_rejected
                      else "LOADED_WITH_REJECTS" if len(rejected) else "LOADED")
            summary = {
                "run_id": run_id, "dataset": dataset, "source_file": path.name,
                "started_at": file_started, "finished_at": _now(),
                "rows_processed": len(df), "rows_valid": len(valid),
                "rows_rejected": len(rejected), "rules_run": len(report.results),
                "rules_failed": sum(r["status"] == "FAIL" for r in report.results),
                "file_status": status,
            }
            file_summaries.append(summary)
            log.info("  -> %s | processed=%d valid=%d rejected=%d rules_failed=%d/%d",
                     status, len(df), len(valid), len(rejected),
                     summary["rules_failed"], summary["rules_run"])

    warehouse.insert_records("dq_validation_results", all_results)
    warehouse.insert_records("dq_pipeline_runs", file_summaries)
    finished = _now()

    run_summary = {
        "run_id": run_id, "started_at": started, "finished_at": finished,
        "input_dir": str(input_dir), "database": str(warehouse.path),
        "backend": warehouse.backend, "log_file": str(log_file),
        "files_processed": len(file_summaries),
        "rows_processed": sum(f["rows_processed"] for f in file_summaries),
        "rows_valid": sum(f["rows_valid"] for f in file_summaries),
        "rows_rejected": sum(f["rows_rejected"] for f in file_summaries),
        "rules_run": len(all_results),
        "rules_failed": sum(r["status"] == "FAIL" for r in all_results),
    }
    report_path = write_report(run_summary, file_summaries, all_results, output_dir / "reports")
    warehouse.close()
    log.info("Run %s finished | rows processed=%d valid=%d rejected=%d | rules failed=%d/%d",
             run_id, run_summary["rows_processed"], run_summary["rows_valid"],
             run_summary["rows_rejected"], run_summary["rules_failed"], run_summary["rules_run"])
    log.info("Report: %s", report_path)
    return run_summary