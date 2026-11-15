"""Command-line entry point:  python run_pipeline.py --input data/raw/batch_1"""
import argparse

from dq_framework.pipeline import run_pipeline

if __name__ == "__main__":
    p = argparse.ArgumentParser(description="Run the data quality pipeline on a folder of CSVs")
    p.add_argument("--input", required=True, help="folder containing incoming CSV files")
    p.add_argument("--config", default="config/rules.yaml")
    p.add_argument("--db", default="warehouse/dq.duckdb")
    p.add_argument("--output", default="output")
    p.add_argument("--backend", default="auto", choices=["auto", "duckdb", "sqlite"])
    a = p.parse_args()
    run_pipeline(a.input, a.config, a.db, a.output, a.backend)