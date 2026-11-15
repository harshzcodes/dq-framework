"""Storage layer: DuckDB is the analytical database.

If the duckdb package is not installed the framework falls back to SQLite
(Python standard library) so the pipeline still runs end to end.
"""
from __future__ import annotations

import logging
from pathlib import Path

import pandas as pd

log = logging.getLogger(__name__)

SQL_TYPES = {"string": "VARCHAR", "integer": "BIGINT", "float": "DOUBLE", "date": "DATE"}

METADATA_DDL = [
    """CREATE TABLE IF NOT EXISTS dq_pipeline_runs (
        run_id VARCHAR, dataset VARCHAR, source_file VARCHAR,
        started_at TIMESTAMP, finished_at TIMESTAMP,
        rows_processed BIGINT, rows_valid BIGINT, rows_rejected BIGINT,
        rules_run BIGINT, rules_failed BIGINT, file_status VARCHAR)""",
    """CREATE TABLE IF NOT EXISTS dq_validation_results (
        run_id VARCHAR, dataset VARCHAR, source_file VARCHAR,
        rule_id VARCHAR, rule_type VARCHAR, column_name VARCHAR, severity VARCHAR,
        status VARCHAR, rows_checked BIGINT, rows_failed BIGINT,
        failure_pct DOUBLE, threshold_pct DOUBLE, details VARCHAR,
        executed_at TIMESTAMP)""",
    """CREATE TABLE IF NOT EXISTS dq_rejected_records (
        run_id VARCHAR, dataset VARCHAR, source_file VARCHAR,
        row_number BIGINT, reject_reasons VARCHAR, record_json VARCHAR,
        rejected_at TIMESTAMP)""",
]
METADATA_TYPES = {
    "dq_pipeline_runs": {"started_at": "TIMESTAMP", "finished_at": "TIMESTAMP"},
    "dq_validation_results": {"executed_at": "TIMESTAMP"},
    "dq_rejected_records": {"rejected_at": "TIMESTAMP"},
}


class Warehouse:
    """Thin wrapper hiding the small differences between DuckDB and SQLite."""

    def __init__(self, db_path: str | Path, backend: str = "auto"):
        db_path = Path(db_path)
        db_path.parent.mkdir(parents=True, exist_ok=True)
        if backend in ("auto", "duckdb"):
            try:
                import duckdb
                self.backend, self.path = "duckdb", db_path
                self.con = duckdb.connect(str(db_path))
            except ImportError:
                if backend == "duckdb":
                    raise
                backend = "sqlite"
                log.warning("duckdb is not installed (pip install duckdb); using SQLite fallback")
        if backend == "sqlite":
            import sqlite3
            self.backend, self.path = "sqlite", db_path.with_suffix(".sqlite")
            self.con = sqlite3.connect(str(self.path))
        log.info("Warehouse: %s (%s)", self.path, self.backend)
        for ddl in METADATA_DDL:
            self.con.execute(ddl)
        self.con.commit()

    # -- helpers -------------------------------------------------------------
    def _placeholder(self, sql_type: str | None) -> str:
        # DuckDB: cast explicitly. SQLite stores ISO text for dates as-is.
        if self.backend == "duckdb" and sql_type:
            return f"CAST(? AS {sql_type})"
        return "?"

    @staticmethod
    def _native(value):
        """Convert pandas/numpy scalars to plain Python values (None for NA)."""
        if value is None or (not isinstance(value, (list, dict)) and pd.isna(value)):
            return None
        if hasattr(value, "isoformat"):               # Timestamp / date / datetime
            return value.isoformat(sep=" ") if hasattr(value, "hour") else value.isoformat()
        if hasattr(value, "item"):                    # numpy scalar
            return value.item()
        return value

    def _insert(self, table: str, columns: list[str], rows: list[tuple],
                types: dict[str, str] | None = None) -> None:
        if not rows:
            return
        types = types or {}
        cols = ", ".join(f'"{c}"' for c in columns)
        marks = ", ".join(self._placeholder(types.get(c)) for c in columns)
        clean = [tuple(self._native(v) for v in row) for row in rows]
        self.con.executemany(f'INSERT INTO "{table}" ({cols}) VALUES ({marks})', clean)

    def insert_records(self, table: str, records: list[dict]) -> None:
        """Insert a list of dicts into one of the dq_* metadata tables."""
        if not records:
            return
        columns = list(records[0])
        self._insert(table, columns, [tuple(r[c] for c in columns) for r in records],
                     METADATA_TYPES.get(table))
        self.con.commit()

    # -- clean data ----------------------------------------------------------
    def load_clean(self, table: str, df: pd.DataFrame, schema: dict[str, str],
                   primary_key: list[str], date_format: str, lineage: dict) -> int:
        """Cast valid rows to the declared schema and upsert them by primary key.

        Deleting existing keys first makes re-running a file idempotent.
        """
        typed = pd.DataFrame(index=df.index)
        for col, kind in schema.items():
            raw = df[col] if col in df.columns else pd.Series(None, index=df.index, dtype=object)
            if kind == "integer":
                typed[col] = pd.to_numeric(raw, errors="coerce").astype("Int64")
            elif kind == "float":
                typed[col] = pd.to_numeric(raw, errors="coerce")
            elif kind == "date":
                typed[col] = pd.to_datetime(raw, format=date_format, errors="coerce").dt.date
            else:
                typed[col] = raw
        for key, value in lineage.items():
            typed[key] = value

        types = {c: SQL_TYPES[k] for c, k in schema.items()}
        types.update({"_run_id": "VARCHAR", "_source_file": "VARCHAR", "_loaded_at": "TIMESTAMP"})
        ddl = ", ".join(f'"{c}" {t}' for c, t in types.items())
        self.con.execute(f'CREATE TABLE IF NOT EXISTS "{table}" ({ddl})')

        if primary_key and len(typed):
            where = " AND ".join(f'"{k}" = ?' for k in primary_key)
            keys = [tuple(self._native(v) for v in row)
                    for row in typed[primary_key].itertuples(index=False, name=None)]
            self.con.executemany(f'DELETE FROM "{table}" WHERE {where}', keys)

        columns = list(typed.columns)
        self._insert(table, columns, list(typed.itertuples(index=False, name=None)), types)
        self.con.commit()
        return len(typed)

    # -- queries -------------------------------------------------------------
    def query(self, sql: str) -> pd.DataFrame:
        cur = self.con.execute(sql)
        columns = [d[0] for d in cur.description]
        return pd.DataFrame(cur.fetchall(), columns=columns)

    def close(self) -> None:
        self.con.close()