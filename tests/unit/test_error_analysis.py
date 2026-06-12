"""Unit tests for src/ml_pipeline/responsible_ai/error_analysis.py."""

from __future__ import annotations

import pandas as pd

from src.common.config import load_config
from src.common.schemas import LABEL_COLUMN
from src.ml_pipeline.evaluate import predict_proba
from src.ml_pipeline.responsible_ai.error_analysis import analyze_slices, compute_error_rate


def test_compute_error_rate_simple_cases() -> None:
    y_true = pd.Series([0, 1, 0, 1])
    all_correct = pd.Series([0, 1, 0, 1])
    all_wrong = pd.Series([1, 0, 1, 0])

    assert compute_error_rate(y_true, all_correct) == 0.0
    assert compute_error_rate(y_true, all_wrong) == 1.0


def test_analyze_slices_structure(model_bundle: dict, test_df: pd.DataFrame) -> None:
    config = load_config(None)
    threshold = config["evaluation"]["decision_threshold"]
    min_slice_size = config.get("responsible_ai", {}).get("error_analysis_min_slice_size", 30)

    y_true = test_df[LABEL_COLUMN].astype(int)
    y_prob = predict_proba(model_bundle, test_df)
    y_pred = pd.Series((y_prob >= threshold).astype(int), index=test_df.index)

    report = analyze_slices(test_df, y_true, y_pred, min_slice_size=min_slice_size)

    assert 0.0 <= report["global_error_rate"] <= 1.0
    assert report["min_slice_size"] == min_slice_size
    assert isinstance(report["slices"], list)
    assert isinstance(report["flagged_slices"], list)
    for s in report["flagged_slices"]:
        assert s["flagged"] is True
        assert s["n"] >= min_slice_size
