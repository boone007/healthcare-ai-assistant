"""Model drift detection.

Tracks two signals over time:

1. **Prediction distribution drift**: a two-sample Kolmogorov-Smirnov test
   comparing the distribution of predicted probabilities in a recent
   production window against a baseline (e.g. the validation-set
   predictions at training time). A low p-value
   (``< monitoring.ks_pvalue_threshold``, default 0.01) indicates the model's
   output distribution has shifted significantly.

2. **Rolling AUC** (when ground-truth labels become available, e.g. 30+ days
   after scoring): recomputed ROC-AUC on recently-labeled encounters,
   compared against the promotion-gate threshold
   (``evaluation.promotion_gate.min_roc_auc``).

Either signal firing triggers the ``ModelDriftDetected`` alert (see
``src/monitoring/alert_rules.json`` and ``docs/runbook-operations.md`` §5.4).

Usage:
    python -m src.monitoring.model_drift_detection \\
        --baseline-predictions outputs/monitoring/baseline_predictions.parquet \\
        --current-predictions data/monitoring/recent_predictions.parquet \\
        --output outputs/monitoring/model_drift_report.json
"""

from __future__ import annotations

import argparse
import json
from pathlib import Path

import pandas as pd
from scipy.stats import ks_2samp
from sklearn.metrics import roc_auc_score

from src.common.config import load_config
from src.common.logging_utils import get_logger

logger = get_logger(__name__)


def compute_prediction_drift(
    baseline_probs: pd.Series, current_probs: pd.Series, pvalue_threshold: float
) -> dict:
    """Two-sample KS test comparing predicted-probability distributions."""
    statistic, pvalue = ks_2samp(baseline_probs.dropna(), current_probs.dropna())
    return {
        "ks_statistic": round(float(statistic), 4),
        "ks_pvalue": round(float(pvalue), 6),
        "pvalue_threshold": pvalue_threshold,
        "drift_detected": pvalue < pvalue_threshold,
    }


def compute_rolling_auc(
    current_probs: pd.Series, current_labels: pd.Series, min_roc_auc: float
) -> dict | None:
    """Compute ROC-AUC on recently-labeled encounters, if labels are available.

    Returns ``None`` if no rows in ``current_labels`` are non-null (i.e. no
    ground truth has become available yet for the current window).
    """
    mask = current_labels.notna()
    if mask.sum() == 0:
        return None

    auc = roc_auc_score(current_labels[mask].astype(int), current_probs[mask])
    return {
        "n_labeled": int(mask.sum()),
        "roc_auc": round(float(auc), 4),
        "min_roc_auc": min_roc_auc,
        "below_threshold": auc < min_roc_auc,
    }


def main() -> None:
    parser = argparse.ArgumentParser(description="Detect model output / performance drift.")
    parser.add_argument("--baseline-predictions", required=True, help="Parquet with column 'readmission_probability'")
    parser.add_argument(
        "--current-predictions",
        required=True,
        help="Parquet with columns 'readmission_probability' and optionally 'readmitted_30d' (ground truth, may be null)",
    )
    parser.add_argument("--config", default="configs/train_config.yaml")
    parser.add_argument("--output", default="outputs/monitoring/model_drift_report.json")
    args = parser.parse_args()

    config = load_config(args.config)
    pvalue_threshold = config.get("monitoring", {}).get("ks_pvalue_threshold", 0.01)
    min_roc_auc = config["evaluation"]["promotion_gate"]["min_roc_auc"]

    baseline = pd.read_parquet(args.baseline_predictions)
    current = pd.read_parquet(args.current_predictions)

    prediction_drift = compute_prediction_drift(
        baseline["readmission_probability"], current["readmission_probability"], pvalue_threshold
    )

    rolling_auc = None
    if "readmitted_30d" in current.columns:
        rolling_auc = compute_rolling_auc(
            current["readmission_probability"], current["readmitted_30d"], min_roc_auc
        )

    drift_detected = prediction_drift["drift_detected"] or bool(rolling_auc and rolling_auc["below_threshold"])

    report = {
        "prediction_drift": prediction_drift,
        "rolling_auc": rolling_auc,
        "drift_detected": drift_detected,
    }

    output_path = Path(args.output)
    output_path.parent.mkdir(parents=True, exist_ok=True)
    with output_path.open("w", encoding="utf-8") as fh:
        json.dump(report, fh, indent=2)

    logger.info("model_drift_report_written", extra={"path": str(output_path), "drift_detected": drift_detected})

    if drift_detected:
        raise SystemExit(1)


if __name__ == "__main__":
    main()
