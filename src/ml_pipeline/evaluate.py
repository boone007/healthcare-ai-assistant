"""Evaluate a trained model on the held-out test set.

Computes discrimination metrics (ROC-AUC, PR-AUC), operating-point metrics
(precision/recall/F1/specificity at one or more thresholds), and calibration
(reliability bins + Brier score). Writes ``metrics.json`` alongside the model
artifact for use by ``register_model.py``'s promotion gate and the
responsible AI report.

Usage:
    python -m src.ml_pipeline.evaluate \\
        --model-path outputs/model.pkl \\
        --data outputs/test.parquet \\
        --config configs/train_config.yaml \\
        --output outputs/metrics.json
"""

from __future__ import annotations

import argparse
import json
from pathlib import Path

import joblib
import numpy as np
import pandas as pd
from sklearn.metrics import (
    average_precision_score,
    brier_score_loss,
    confusion_matrix,
    precision_recall_curve,
    roc_auc_score,
)

from src.common.config import load_config
from src.common.logging_utils import get_logger
from src.common.schemas import LABEL_COLUMN
from src.ml_pipeline.train import prepare_xy

logger = get_logger(__name__)


def predict_proba(model_bundle: dict, df: pd.DataFrame) -> np.ndarray:
    """Return the predicted readmission probability for each row of ``df``."""
    X, _ = prepare_xy(
        df.assign(**{LABEL_COLUMN: df.get(LABEL_COLUMN, 0)}),
        algorithm=model_bundle["algorithm"],
        categorical_dtypes=model_bundle["categorical_categories"],
    )
    # Align columns for the xgboost one-hot path in case the test set is
    # missing a category present at training time (or vice versa).
    if model_bundle["algorithm"] == "xgboost":
        train_columns = model_bundle.get("train_columns")
        if train_columns is not None:
            X = X.reindex(columns=train_columns, fill_value=0)
    return model_bundle["model"].predict_proba(X)[:, 1]


def compute_calibration(y_true: np.ndarray, y_prob: np.ndarray, n_bins: int = 10) -> list[dict]:
    """Compute a reliability diagram as a list of bin summaries."""
    bins = np.linspace(0, 1, n_bins + 1)
    bin_ids = np.digitize(y_prob, bins[1:-1])

    reliability = []
    for b in range(n_bins):
        mask = bin_ids == b
        if mask.sum() == 0:
            continue
        reliability.append(
            {
                "bin_lower": round(float(bins[b]), 2),
                "bin_upper": round(float(bins[b + 1]), 2),
                "count": int(mask.sum()),
                "mean_predicted": round(float(y_prob[mask].mean()), 4),
                "observed_rate": round(float(y_true[mask].mean()), 4),
            }
        )
    return reliability


def compute_threshold_metrics(y_true: np.ndarray, y_prob: np.ndarray, threshold: float) -> dict:
    """Compute precision/recall/F1/specificity at a given decision threshold."""
    y_pred = (y_prob >= threshold).astype(int)
    tn, fp, fn, tp = confusion_matrix(y_true, y_pred, labels=[0, 1]).ravel()

    precision = tp / (tp + fp) if (tp + fp) > 0 else 0.0
    recall = tp / (tp + fn) if (tp + fn) > 0 else 0.0
    specificity = tn / (tn + fp) if (tn + fp) > 0 else 0.0
    f1 = 2 * precision * recall / (precision + recall) if (precision + recall) > 0 else 0.0

    return {
        "threshold": threshold,
        "precision": round(precision, 4),
        "recall": round(recall, 4),
        "specificity": round(specificity, 4),
        "f1": round(f1, 4),
        "confusion_matrix": {"tn": int(tn), "fp": int(fp), "fn": int(fn), "tp": int(tp)},
    }


def find_high_recall_threshold(y_true: np.ndarray, y_prob: np.ndarray, precision_floor: float) -> float:
    """Find the lowest threshold that keeps precision >= ``precision_floor``.

    Used to surface a clinically-tuned operating point that maximizes
    recall (sensitivity) while maintaining a minimum precision, per
    ``docs/ml-design.md`` §6.
    """
    precisions, recalls, thresholds = precision_recall_curve(y_true, y_prob)
    # precision_recall_curve returns thresholds of length len(precisions)-1
    candidates = [
        (thresholds[i], recalls[i])
        for i in range(len(thresholds))
        if precisions[i] >= precision_floor
    ]
    if not candidates:
        return 0.5
    # Among candidates meeting the precision floor, pick the one maximizing recall.
    best = max(candidates, key=lambda c: c[1])
    return round(float(best[0]), 4)


def evaluate(model_bundle: dict, test_df: pd.DataFrame, config: dict) -> dict:
    """Compute the full evaluation metrics dictionary for ``test_df``."""
    y_true = test_df[LABEL_COLUMN].astype(int).to_numpy()
    y_prob = predict_proba(model_bundle, test_df)

    eval_cfg = config["evaluation"]
    default_threshold = eval_cfg["decision_threshold"]
    precision_floor = eval_cfg.get("high_recall_precision_floor", 0.30)

    high_recall_threshold = find_high_recall_threshold(y_true, y_prob, precision_floor)

    metrics = {
        "n_rows": len(test_df),
        "positive_rate": round(float(y_true.mean()), 4),
        "roc_auc": round(float(roc_auc_score(y_true, y_prob)), 4),
        "pr_auc": round(float(average_precision_score(y_true, y_prob)), 4),
        "brier_score": round(float(brier_score_loss(y_true, y_prob)), 4),
        "calibration": compute_calibration(y_true, y_prob),
        "operating_points": {
            "default": compute_threshold_metrics(y_true, y_prob, default_threshold),
            "high_recall": compute_threshold_metrics(y_true, y_prob, high_recall_threshold),
        },
    }

    gate = eval_cfg["promotion_gate"]
    metrics["promotion_gate"] = {
        "min_roc_auc": gate["min_roc_auc"],
        "min_pr_auc": gate["min_pr_auc"],
        "max_brier_score": gate["max_brier_score"],
        "passes_roc_auc": metrics["roc_auc"] >= gate["min_roc_auc"],
        "passes_pr_auc": metrics["pr_auc"] >= gate["min_pr_auc"],
        "passes_brier_score": metrics["brier_score"] <= gate["max_brier_score"],
    }

    logger.info("evaluation_complete", extra={k: v for k, v in metrics.items() if not isinstance(v, (list, dict))})
    return metrics


def main() -> None:
    parser = argparse.ArgumentParser(description="Evaluate a trained model on the test set.")
    parser.add_argument("--model-path", required=True, help="Path to the model artifact (.pkl)")
    parser.add_argument("--data", required=True, help="Path to the test feature table (.parquet)")
    parser.add_argument("--config", default="configs/train_config.yaml", help="Path to training config YAML")
    parser.add_argument("--output", default="outputs/metrics.json", help="Path to write metrics JSON")
    args = parser.parse_args()

    config = load_config(args.config)
    model_bundle = joblib.load(args.model_path)
    test_df = pd.read_parquet(args.data)

    metrics = evaluate(model_bundle, test_df, config)

    output_path = Path(args.output)
    output_path.parent.mkdir(parents=True, exist_ok=True)
    with output_path.open("w", encoding="utf-8") as fh:
        json.dump(metrics, fh, indent=2)

    logger.info("metrics_written", extra={"path": str(output_path)})


if __name__ == "__main__":
    main()
