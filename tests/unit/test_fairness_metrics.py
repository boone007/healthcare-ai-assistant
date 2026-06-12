"""Unit tests for src/ml_pipeline/responsible_ai/fairness_metrics.py."""

from __future__ import annotations

import pandas as pd

from src.common.config import load_config
from src.ml_pipeline.responsible_ai.fairness_metrics import assess_fairness, compute_group_metrics


def test_compute_group_metrics_identical_groups_have_zero_difference() -> None:
    y_true = pd.Series([0, 1, 0, 1, 0, 1, 0, 1])
    y_pred = pd.Series([0, 1, 0, 1, 0, 1, 0, 1])
    sensitive = pd.Series(["A", "A", "A", "A", "B", "B", "B", "B"])

    report = compute_group_metrics(y_true, y_pred, sensitive)

    assert report["demographic_parity_difference"] == 0.0
    assert report["equalized_odds_difference"] == 0.0
    assert set(report["by_group"]) == {"A", "B"}


def test_compute_group_metrics_detects_demographic_parity_difference() -> None:
    y_true = pd.Series([0, 0, 0, 0, 0, 0, 0, 0])
    # Group A: model never selects positive class. Group B: always selects.
    y_pred = pd.Series([0, 0, 0, 0, 1, 1, 1, 1])
    sensitive = pd.Series(["A", "A", "A", "A", "B", "B", "B", "B"])

    report = compute_group_metrics(y_true, y_pred, sensitive)

    assert report["demographic_parity_difference"] == 1.0


def test_assess_fairness_report_structure(model_bundle: dict, test_df: pd.DataFrame) -> None:
    config = load_config(None)
    threshold = config["evaluation"]["decision_threshold"]

    report = assess_fairness(model_bundle, test_df, config, threshold)

    assert report["decision_threshold"] == threshold
    for col in ["sex", "age_band", "ethnicity"]:
        assert col in report["groups"]
        group_report = report["groups"][col]
        assert "demographic_parity_difference" in group_report
        assert "equalized_odds_difference" in group_report
        assert "passes_equalized_odds_gate" in group_report
