"""Data drift detection.

Compares the distribution of features in a recent production scoring window
against the training baseline distribution using the Population Stability
Index (PSI) for each feature. A feature with ``PSI > psi_threshold``
(default 0.2, per ``configs/train_config.yaml: monitoring.psi_threshold``)
is flagged as drifted, triggering the ``DataDriftDetected`` alert
(see ``src/monitoring/alert_rules.json`` and ``docs/runbook-operations.md`` §5.3).

Usage:
    python -m src.monitoring.data_drift_detection \\
        --baseline outputs/train.parquet \\
        --current data/monitoring/recent_scoring_inputs.parquet \\
        --output outputs/monitoring/drift_report.json
"""

from __future__ import annotations

import argparse
import json
from pathlib import Path

import numpy as np
import pandas as pd

from src.common.config import load_config
from src.common.logging_utils import get_logger
from src.common.schemas import CATEGORICAL_COLUMNS, MODEL_FEATURE_COLUMNS

logger = get_logger(__name__)

NUMERIC_COLUMNS = [c for c in MODEL_FEATURE_COLUMNS if c not in CATEGORICAL_COLUMNS]


def _psi_numeric(baseline: pd.Series, current: pd.Series, n_bins: int = 10) -> float:
    """Compute PSI for a numeric feature using baseline-derived quantile bins."""
    baseline = baseline.dropna()
    current = current.dropna()

    quantiles = np.linspace(0, 1, n_bins + 1)
    bin_edges = np.unique(baseline.quantile(quantiles).to_numpy())
    if len(bin_edges) < 3:
        # Degenerate (near-constant) feature; treat as no drift.
        return 0.0

    bin_edges[0] = -np.inf
    bin_edges[-1] = np.inf

    baseline_counts = pd.cut(baseline, bins=bin_edges).value_counts(normalize=True).sort_index()
    current_counts = pd.cut(current, bins=bin_edges).value_counts(normalize=True).sort_index()

    return _psi_from_distributions(baseline_counts, current_counts)


def _psi_categorical(baseline: pd.Series, current: pd.Series) -> float:
    """Compute PSI for a categorical feature using observed category frequencies."""
    baseline_counts = baseline.value_counts(normalize=True)
    current_counts = current.value_counts(normalize=True)
    return _psi_from_distributions(baseline_counts, current_counts)


def _psi_from_distributions(baseline_pct: pd.Series, current_pct: pd.Series, epsilon: float = 1e-4) -> float:
    """Sum the PSI contributions across the union of bins/categories."""
    index = baseline_pct.index.union(current_pct.index)
    b = baseline_pct.reindex(index, fill_value=0).clip(lower=epsilon)
    c = current_pct.reindex(index, fill_value=0).clip(lower=epsilon)
    return float(((c - b) * np.log(c / b)).sum())


def compute_drift_report(baseline: pd.DataFrame, current: pd.DataFrame, psi_threshold: float) -> dict:
    """Compute per-feature PSI and flag drifted features."""
    features: dict[str, dict] = {}

    for col in MODEL_FEATURE_COLUMNS:
        if col not in baseline.columns or col not in current.columns:
            continue
        if col in CATEGORICAL_COLUMNS:
            psi = _psi_categorical(baseline[col].astype(str), current[col].astype(str))
        else:
            psi = _psi_numeric(baseline[col], current[col])

        features[col] = {
            "psi": round(psi, 4),
            "drifted": psi > psi_threshold,
        }

    drifted_features = [name for name, info in features.items() if info["drifted"]]
    logger.info(
        "data_drift_report_complete",
        extra={"features_evaluated": len(features), "drifted_features": drifted_features},
    )

    return {
        "psi_threshold": psi_threshold,
        "baseline_rows": len(baseline),
        "current_rows": len(current),
        "features": features,
        "drifted_features": drifted_features,
        "drift_detected": len(drifted_features) > 0,
    }


def main() -> None:
    parser = argparse.ArgumentParser(description="Detect data drift between a baseline and current dataset.")
    parser.add_argument("--baseline", required=True, help="Path to the training baseline feature table (.parquet)")
    parser.add_argument("--current", required=True, help="Path to recent production scoring inputs (.parquet)")
    parser.add_argument("--config", default="configs/train_config.yaml")
    parser.add_argument("--output", default="outputs/monitoring/drift_report.json")
    args = parser.parse_args()

    config = load_config(args.config)
    psi_threshold = config.get("monitoring", {}).get("psi_threshold", 0.2)

    baseline = pd.read_parquet(args.baseline)
    current = pd.read_parquet(args.current)

    report = compute_drift_report(baseline, current, psi_threshold)

    output_path = Path(args.output)
    output_path.parent.mkdir(parents=True, exist_ok=True)
    with output_path.open("w", encoding="utf-8") as fh:
        json.dump(report, fh, indent=2)

    logger.info("drift_report_written", extra={"path": str(output_path), "drift_detected": report["drift_detected"]})

    if report["drift_detected"]:
        raise SystemExit(1)


if __name__ == "__main__":
    main()
