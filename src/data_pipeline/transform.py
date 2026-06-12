"""Transform stage: clean validated raw data and produce the curated feature table.

Usage:
    python -m src.data_pipeline.transform \\
        --input data/raw/encounters.csv \\
        --output data/processed/features.parquet
"""

from __future__ import annotations

import argparse

import pandas as pd

from src.common.logging_utils import get_logger
from src.common.utils import read_table, timer, write_table
from src.data_pipeline.feature_engineering import engineer_features

logger = get_logger(__name__)


@timer
def clean_raw_encounters(df: pd.DataFrame) -> pd.DataFrame:
    """Apply basic cleaning prior to feature engineering.

    - Drops exact-duplicate encounter rows.
    - Drops rows missing the label when present (training data only); rows
      without ``readmitted_30d`` are assumed to be inference-time requests
      and are passed through unchanged.
    - Coerces date columns to ``datetime64``.
    """
    out = df.drop_duplicates(subset=["encounter_id"]).copy()

    for date_col in ("admit_date", "discharge_date"):
        if date_col in out.columns:
            out[date_col] = pd.to_datetime(out[date_col])

    if "readmitted_30d" in out.columns:
        before = len(out)
        out = out.dropna(subset=["readmitted_30d"])
        dropped = before - len(out)
        if dropped:
            logger.warning("dropped_rows_missing_label", extra={"dropped_rows": dropped})

    return out


@timer
def transform(df: pd.DataFrame) -> pd.DataFrame:
    """Run the full transform: clean -> feature engineer."""
    cleaned = clean_raw_encounters(df)
    features = engineer_features(cleaned, keep_ethnicity=True)
    logger.info("transform_complete", extra={"rows": len(features), "columns": len(features.columns)})
    return features


def main() -> None:
    parser = argparse.ArgumentParser(description="Transform raw encounters into curated features.")
    parser.add_argument("--input", required=True, help="Path to validated raw data (.csv or .parquet)")
    parser.add_argument("--output", required=True, help="Path to write curated features (.parquet recommended)")
    args = parser.parse_args()

    raw = read_table(args.input)
    features = transform(raw)
    write_table(features, args.output)


if __name__ == "__main__":
    main()
