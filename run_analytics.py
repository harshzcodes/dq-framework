"""Run every query in sql/analytics.sql and print (and optionally save) the results."""
import argparse
import re
from pathlib import Path

import pandas as pd

from dq_framework.storage import Warehouse

if __name__ == "__main__":
    p = argparse.ArgumentParser()
    p.add_argument("--db", default="warehouse/dq.duckdb")
    p.add_argument("--sql", default="sql/analytics.sql")
    p.add_argument("--backend", default="auto", choices=["auto", "duckdb", "sqlite"])
    p.add_argument("--save", help="also write the results to this Markdown file")
    a = p.parse_args()

    pd.set_option("display.width", 200, "display.max_columns", 20, "display.max_colwidth", 40)
    wh = Warehouse(a.db, a.backend)
    blocks = re.split(r"^-- name:\s*", Path(a.sql).read_text(encoding="utf-8"), flags=re.M)[1:]
    out = []
    for block in blocks:
        name, _, sql = block.partition("\n")
        text = wh.query(sql.strip().rstrip(";")).to_string(index=False)
        print(f"\n=== {name.strip()} ===\n{text}")
        out.append(f"## {name.strip()}\n\n```\n{text}\n```\n")
    if a.save:
        Path(a.save).parent.mkdir(parents=True, exist_ok=True)
        Path(a.save).write_text("# Data quality analytics\n\n" + "\n".join(out), encoding="utf-8")
    wh.close()