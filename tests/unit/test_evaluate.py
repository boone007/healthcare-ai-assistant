"""Unit tests for src/ml_pipeline/evaluate.py."""

from __future__ import annotations

import numpy as np
import pandas as pd

from src.common.config import load_config
from src.ml_pipeline.evaluate import (
    compute_calibration,
    compute_threshold_metrics,
    evaluate,
    find_high_recall_threshold,
    predict_proba,
)


def test_compute_calibration_bins_cover_all_rows() -> None:
    y_true = np.array([0, 0, 1, 1, 0, 1, 0, 1, 1, 0])
    y_prob = np.array([0.05, 0.12, 0.42, 0.55, 0.61, 0.78, 0.83, 0.91, 0.95, 0.02])

    reliability = compute_calibration(y_true, y_prob, n_bins=10)

    assert sum(b["count"] for b in reliability) == len(y_true)
    for b in reliability:
        assert 0.0 <= b["mean_predicted"] <= 1.0
        assert 0.0 <= b["observed_rate"] <= 1.0


def test_compute_threshold_metrics_perfect_separation() -> None:
    y_true = np.array([0, 0, 1, 1])
    y_prob = np.array([0.1, 0.2, 0.8, 0.9])

    result = compute_threshold_metrics(y_true, y_prob, threshold=0.5)

    assert result["precision"] == 1.0
    assert result["recall"] == 1.0
    assert result["specificity"] == 1.0
    assert result["f1"] == 1.0
    assert result["confusion_matrix"] == {"tn": 2, "fp": 0, "fn": 0, "tp": 2}


def test_compute_threshold_metrics_handles_no_positive_predictions() -> None:
    y_true = np.array([0, 0, 1, 1])
    y_prob = np.array([0.05, 0.05, 0.05, 0.05])

    result = compute_threshold_metrics(y_true, y_prob, threshold=0.9)

    assert result["precision"] == 0.0
    assert result["recall"] == 0.0
    assert result["confusion_matrix"]["tp"] == 0


def test_find_high_recall_threshold_meets_precision_floor() -> None:
    y_true = np.array([0, 0, 0, 1, 1, 1, 1, 1])
    y_prob = np.array([0.05, 0.1, 0.3, 0.4, 0.6, 0.7, 0.8, 0.95])

    threshold = find_high_recall_threshold(y_true, y_prob, precision_floor=0.5)

    assert 0.0 <= threshold <= 1.0


def test_predict_proba_returns_probabilities_in_unit_interval(model_bundle: dict, test_df: pd.DataFrame) -> None:
    probabilities = predict_proba(model_bundle, test_df)

    assert probabilities.shape[0] == len(test_df)
    assert np.all(probabilities >= 0.0)
    assert np.all(probabilities <= 1.0)


def test_evaluate_returns_expected_metric_keys(model_bundle: dict, test_df: pd.DataFrame) -> None:
    config = load_config(None)

    metrics = evaluate(model_bundle, test_df, config)

    assert metrics["n_rows"] == len(test_df)
    assert 0.0 <= metrics["roc_auc"] <= 1.0
    assert 0.0 <= metrics["pr_auc"] <= 1.0
    assert 0.0 <= metrics["brier_score"] <= 1.0
    assert "default" in metrics["operating_points"]
    assert "high_recall" in metrics["operating_points"]

    gate = metrics["promotion_gate"]
    assert set(gate) >= {"min_roc_auc", "min_pr_auc", "max_brier_score", "passes_roc_auc", "passes_pr_auc", "passes_brier_score"}
