"""Unit tests for src/monitoring/data_drift_detection.py and model_drift_detection.py."""

from __future__ import annotations

import numpy as np
import pandas as pd

from src.monitoring.data_drift_detection import _psi_categorical, _psi_numeric, compute_drift_report
from src.monitoring.model_drift_detection import compute_prediction_drift, compute_rolling_auc


def _baseline_numeric_series(n: int = 1000) -> pd.Series:
    rng = np.random.default_rng(0)
    return pd.Series(rng.normal(50, 10, size=n))


def test_psi_numeric_is_near_zero_for_identical_distributions() -> None:
    baseline = _baseline_numeric_series()
    current = baseline.copy()

    psi = _psi_numeric(baseline, current)

    assert psi < 1e-6


def test_psi_numeric_is_large_for_shifted_distribution() -> None:
    baseline = _baseline_numeric_series()
    rng = np.random.default_rng(1)
    current = pd.Series(rng.normal(80, 10, size=1000))  # large mean shift

    psi = _psi_numeric(baseline, current)

    assert psi > 0.2


def test_psi_categorical_is_near_zero_for_identical_distributions() -> None:
    baseline = pd.Series(["A"] * 500 + ["B"] * 300 + ["C"] * 200)
    current = baseline.copy()

    psi = _psi_categorical(baseline, current)

    assert psi < 1e-6


def test_psi_categorical_is_large_for_shifted_distribution() -> None:
    baseline = pd.Series(["A"] * 500 + ["B"] * 300 + ["C"] * 200)
    current = pd.Series(["A"] * 100 + ["B"] * 100 + ["C"] * 800)

    psi = _psi_categorical(baseline, current)

    assert psi > 0.2


def test_compute_drift_report_flags_drifted_features(engineered_df: pd.DataFrame) -> None:
    baseline = engineered_df.copy()
    current = engineered_df.copy()
    # Inject a large shift into a numeric feature.
    current["bmi"] = current["bmi"] + 50

    report = compute_drift_report(baseline, current, psi_threshold=0.2)

    assert report["drift_detected"] is True
    assert "bmi" in report["drifted_features"]
    assert report["features"]["bmi"]["drifted"] is True


def test_compute_drift_report_no_drift_for_identical_data(engineered_df: pd.DataFrame) -> None:
    report = compute_drift_report(engineered_df, engineered_df.copy(), psi_threshold=0.2)

    assert report["drift_detected"] is False
    assert report["drifted_features"] == []


def test_compute_prediction_drift_detects_distribution_shift() -> None:
    rng = np.random.default_rng(0)
    baseline = pd.Series(rng.uniform(0, 0.3, size=500))
    current = pd.Series(rng.uniform(0.6, 1.0, size=500))

    result = compute_prediction_drift(baseline, current, pvalue_threshold=0.01)

    assert result["drift_detected"] is True
    assert result["ks_pvalue"] < 0.01


def test_compute_prediction_drift_no_drift_for_identical_distributions() -> None:
    rng = np.random.default_rng(0)
    baseline = pd.Series(rng.uniform(0, 1, size=500))
    current = baseline.copy()

    result = compute_prediction_drift(baseline, current, pvalue_threshold=0.01)

    assert result["drift_detected"] is False
    assert result["ks_statistic"] == 0.0


def test_compute_rolling_auc_returns_none_without_labels() -> None:
    current_probs = pd.Series([0.1, 0.9, 0.4])
    current_labels = pd.Series([None, None, None])

    result = compute_rolling_auc(current_probs, current_labels, min_roc_auc=0.7)

    assert result is None


def test_compute_rolling_auc_flags_below_threshold() -> None:
    # Predictions inversely related to labels -> low AUC.
    current_probs = pd.Series([0.9, 0.8, 0.2, 0.1])
    current_labels = pd.Series([0, 0, 1, 1])

    result = compute_rolling_auc(current_probs, current_labels, min_roc_auc=0.7)

    assert result["n_labeled"] == 4
    assert result["below_threshold"] is True
