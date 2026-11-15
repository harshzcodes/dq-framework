"""Ingestion: find the CSV files for a dataset and read them without losing evidence."""
from __future__ import annotations

import logging
from pathlib import Path

import pandas as pd

log = logging.getLogger(__name__)

NULL_TOKENS = {"", "null", "none", "nan", "n/a", "na"}


def discover_files(input_dir: str | Path, pattern: str) -> list[Path]:
    """Return every file in input_dir matching the dataset's glob pattern."""
    return sorted(p for p in Path(input_dir).glob(pattern) if p.is_file())


def read_csv(path: str | Path) -> pd.DataFrame:
    """Read one CSV as raw strings, trim whitespace, normalise null markers to NA."""
    df = pd.read_csv(path, dtype=str, keep_default_na=False, encoding="utf-8-sig")
    df.columns = [c.strip() for c in df.columns]
    for col in df.columns:
        stripped = df[col].str.strip()
        df[col] = stripped.astype(object).mask(stripped.str.lower().isin(NULL_TOKENS), None)
    log.info("Read %s: %d rows, %d columns", Path(path).name, len(df), len(df.columns))
    return df