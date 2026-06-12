"""SHAP-based model explainability.

Computes global feature importance (mean absolute SHAP value across the test
set) and, for a small sample of rows, the top contributing factors for each
individual prediction — the same mechanism used to populate ``top_factors``
in the scoring API response (see ``docs/api-design.md`` §3.1).

Usage:
    python -m src.ml_pipeline.responsible_ai.shap_explainability \\
        --model-path outputs/model.pkl \\
        --data outputs/test.parquet \\
        --output outputs/responsible_ai/shap_report.json
"""

from __future__ import annotations

import argparse
import json
from pathlib import Path

import joblib
import numpy as np
import pandas as pd

from src.common.config import load_config
from src.common.logging_utils import get_logger
from src.common.schemas import LABEL_COLUMN
from src.ml_pipeline.train import prepare_xy

logger = get_logger(__name__)


def compute_shap_values(model_bundle: dict, X: pd.DataFrame) -> np.ndarray:
    """Compute SHAP values for ``X`` using a TreeExplainer on the underlying model."""
    import shap

    explainer = shap.TreeExplainer(model_bundle["model"])
    shap_values = explainer.shap_values(X)

    # Binary classifiers may return a list [class_0, class_1] or a single array
    # depending on the SHAP/model version; normalize to the positive-class array.
    if isinstance(shap_values, list):
        shap_values = shap_values[1]

    return np.asarray(shap_values)


def global_feature_importance(shap_values: np.ndarray, feature_names: list[str]) -> list[dict]:
    """Rank features by mean absolute SHAP value across all rows."""
    mean_abs = np.abs(shap_values).mean(axis=0)
    ranking = sorted(zip(feature_names, mean_abs), key=lambda x: x[1], reverse=True)
    return [{"feature": name, "mean_abs_shap": round(float(value), 4)} for name, value in ranking]


def top_factors_for_row(shap_row: np.ndarray, feature_names: list[str], top_n: int = 3) -> list[dict]:
    """Return the top-N SHAP contributors (by absolute value) for a single row."""
    pairs = sorted(zip(feature_names, shap_row), key=lambda x: abs(x[1]), reverse=True)[:top_n]
    return [{"feature": name, "shap_value": round(float(value), 4)} for name, value in pairs]


def main() -> None:
    parser = argparse.ArgumentParser(description="Generate a SHAP explainability report.")
    parser.add_argument("--model-path", required=True, help="Path to the model artifact (.pkl)")
    parser.add_argument("--data", required=True, help="Path to a feature table (.parquet) to explain")
    parser.add_argument("--config", default="configs/train_config.yaml", help="Path to training config YAML")
    parser.add_argument("--output", default="outputs/responsible_ai/shap_report.json", help="Output JSON path")
    parser.add_argument("--sample-rows", type=int, default=5, help="Number of rows to include local explanations for")
    args = parser.parse_args()

    config = load_config(args.config)
    sample_size = config.get("responsible_ai", {}).get("shap_sample_size", 1000)

    model_bundle = joblib.load(args.model_path)
    df = pd.read_parquet(args.data)
    if len(df) > sample_size:
        df = df.sample(n=sample_size, random_state=model_bundle.get("random_seed", 42))

    X, _ = prepare_xy(
        df.assign(**{LABEL_COLUMN: df.get(LABEL_COLUMN, 0)}),
        algorithm=model_bundle["algorithm"],
        categorical_dtypes=model_bundle["categorical_categories"],
    )
    if model_bundle["algorithm"] == "xgboost" and model_bundle.get("train_columns"):
        X = X.reindex(columns=model_bundle["train_columns"], fill_value=0)

    shap_values = compute_shap_values(model_bundle, X)

    report = {
        "n_rows_explained": len(X),
        "global_feature_importance": global_feature_importance(shap_values, list(X.columns)),
        "sample_local_explanations": [
            {
                "encounter_id": str(df.iloc[i]["encounter_id"]),
                "top_factors": top_factors_for_row(shap_values[i], list(X.columns)),
            }
            for i in range(min(args.sample_rows, len(X)))
        ],
    }

    output_path = Path(args.output)
    output_path.parent.mkdir(parents=True, exist_ok=True)
    with output_path.open("w", encoding="utf-8") as fh:
        json.dump(report, fh, indent=2)

    logger.info("shap_report_written", extra={"path": str(output_path), "rows_explained": len(X)})


if __name__ == "__main__":
    main()
