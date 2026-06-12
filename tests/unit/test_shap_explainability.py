"""Unit tests for src/ml_pipeline/responsible_ai/shap_explainability.py."""

from __future__ import annotations

import numpy as np
import pandas as pd

from src.common.schemas import LABEL_COLUMN
from src.ml_pipeline.responsible_ai.shap_explainability import (
    compute_shap_values,
    global_feature_importance,
    top_factors_for_row,
)
from src.ml_pipeline.train import prepare_xy


def test_compute_shap_values_and_global_importance(model_bundle: dict, test_df: pd.DataFrame) -> None:
    X, _ = prepare_xy(
        test_df.assign(**{LABEL_COLUMN: test_df.get(LABEL_COLUMN, 0)}),
        algorithm=model_bundle["algorithm"],
        categorical_dtypes=model_bundle["categorical_categories"],
    )

    shap_values = compute_shap_values(model_bundle, X)
    assert shap_values.shape == (len(X), X.shape[1])

    importance = global_feature_importance(shap_values, list(X.columns))
    assert len(importance) == X.shape[1]
    # Sorted descending by mean absolute SHAP value.
    values = [item["mean_abs_shap"] for item in importance]
    assert values == sorted(values, reverse=True)
    for item in importance:
        assert item["mean_abs_shap"] >= 0.0


def test_top_factors_for_row_returns_top_n_by_magnitude() -> None:
    shap_row = np.array([0.5, -0.9, 0.1, 0.3, -0.2])
    feature_names = ["age", "prior_admissions_12mo", "bmi", "charlson_index", "los_bucket"]

    top_factors = top_factors_for_row(shap_row, feature_names, top_n=3)

    assert len(top_factors) == 3
    assert top_factors[0]["feature"] == "prior_admissions_12mo"
    assert top_factors[0]["shap_value"] == -0.9
    magnitudes = [abs(f["shap_value"]) for f in top_factors]
    assert magnitudes == sorted(magnitudes, reverse=True)
