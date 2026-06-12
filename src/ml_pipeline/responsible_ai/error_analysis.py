"""Slice-based error analysis.

Computes the model's error rate within configurable cohort "slices"
(combinations of categorical feature values) and flags slices whose error
rate is materially higher than the global error rate, surfacing
underperforming cohorts for the responsible AI report
(``docs/responsible-ai-report.md`` §4).

Usage:
    python -m src.ml_pipeline.responsible_ai.error_analysis \\
        --model-path outputs/model.pkl \\
        --data outputs/test.parquet \\
        --output outputs/responsible_ai/error_analysis.json
"""

from __future__ import annotations

import argparse
import json
from itertools import combinations
from pathlib import Path

import joblib
import pandas as pd

from src.common.config import load_config
from src.common.logging_utils import get_logger
from src.common.schemas import LABEL_COLUMN
from src.ml_pipeline.evaluate import predict_proba

logger = get_logger(__name__)

# Categorical columns considered for slice generation.
SLICE_COLUMNS = ["admission_type", "discharge_disposition", "insurance_type", "age_band", "los_bucket"]


def compute_error_rate(y_true: pd.Series, y_pred: pd.Series) -> float:
    """Fraction of misclassified rows."""
    return float((y_true != y_pred).mean())


def analyze_slices(
    df: pd.DataFrame,
    y_true: pd.Series,
    y_pred: pd.Series,
    min_slice_size: int,
    elevation_factor: float = 1.25,
) -> dict:
    """Compute single-column and pairwise-column slice error rates.

    A slice is "flagged" if it has at least ``min_slice_size`` rows and its
    error rate exceeds the global error rate by more than ``elevation_factor``
    (default: 25% relative increase).
    """
    global_error_rate = compute_error_rate(y_true, y_pred)
    misclassified = (y_true != y_pred)

    slices: list[dict] = []

    # Single-column slices
    for col in SLICE_COLUMNS:
        if col not in df.columns:
            continue
        for value, group_idx in df.groupby(col).groups.items():
            n = len(group_idx)
            if n < min_slice_size:
                continue
            error_rate = float(misclassified.loc[group_idx].mean())
            slices.append(
                {
                    "slice": {col: str(value)},
                    "n": n,
                    "error_rate": round(error_rate, 4),
                    "global_error_rate": round(global_error_rate, 4),
                    "flagged": error_rate > global_error_rate * elevation_factor,
                }
            )

    # Pairwise-column slices (limited to avoid combinatorial explosion)
    for col_a, col_b in combinations(SLICE_COLUMNS, 2):
        if col_a not in df.columns or col_b not in df.columns:
            continue
        for (val_a, val_b), group_idx in df.groupby([col_a, col_b]).groups.items():
            n = len(group_idx)
            if n < min_slice_size:
                continue
            error_rate = float(misclassified.loc[group_idx].mean())
            if error_rate > global_error_rate * elevation_factor:
                slices.append(
                    {
                        "slice": {col_a: str(val_a), col_b: str(val_b)},
                        "n": n,
                        "error_rate": round(error_rate, 4),
                        "global_error_rate": round(global_error_rate, 4),
                        "flagged": True,
                    }
                )

    flagged = [s for s in slices if s["flagged"]]
    logger.info(
        "error_analysis_complete",
        extra={"global_error_rate": round(global_error_rate, 4), "slices_evaluated": len(slices), "slices_flagged": len(flagged)},
    )

    return {
        "global_error_rate": round(global_error_rate, 4),
        "min_slice_size": min_slice_size,
        "slices": sorted(slices, key=lambda s: s["error_rate"], reverse=True),
        "flagged_slices": sorted(flagged, key=lambda s: s["error_rate"], reverse=True),
    }


def main() -> None:
    parser = argparse.ArgumentParser(description="Run slice-based error analysis.")
    parser.add_argument("--model-path", required=True, help="Path to the model artifact (.pkl)")
    parser.add_argument("--data", required=True, help="Path to the test feature table (.parquet)")
    parser.add_argument("--config", default="configs/train_config.yaml", help="Path to training config YAML")
    parser.add_argument("--output", default="outputs/responsible_ai/error_analysis.json", help="Output JSON path")
    args = parser.parse_args()

    config = load_config(args.config)
    model_bundle = joblib.load(args.model_path)
    df = pd.read_parquet(args.data)

    threshold = config["evaluation"]["decision_threshold"]
    min_slice_size = config.get("responsible_ai", {}).get("error_analysis_min_slice_size", 30)

    y_true = df[LABEL_COLUMN].astype(int)
    y_prob = predict_proba(model_bundle, df)
    y_pred = pd.Series((y_prob >= threshold).astype(int), index=df.index)

    report = analyze_slices(df, y_true, y_pred, min_slice_size=min_slice_size)

    output_path = Path(args.output)
    output_path.parent.mkdir(parents=True, exist_ok=True)
    with output_path.open("w", encoding="utf-8") as fh:
        json.dump(report, fh, indent=2)

    logger.info("error_analysis_written", extra={"path": str(output_path)})


if __name__ == "__main__":
    main()
