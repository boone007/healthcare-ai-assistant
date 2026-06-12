"""End-to-end integration test for the data + ML pipeline.

Exercises the full chain on a small synthetic dataset, writing intermediate
artifacts to disk exactly as the AML pipeline steps in
``src/ml_pipeline/pipeline_definition.py`` do:

    ingest -> validate -> transform -> train -> evaluate
           -> responsible AI (fairness, error analysis, SHAP)
           -> promotion gate check

This does not require any Azure credentials or services.
"""

from __future__ import annotations

import json
from datetime import date
from pathlib import Path

import joblib
import pandas as pd

from src.common.config import load_config
from src.common.schemas import CATEGORICAL_COLUMNS, LABEL_COLUMN, MODEL_FEATURE_COLUMNS
from src.common.utils import read_table, write_table
from src.data_pipeline.ingest import generate_synthetic_encounters
from src.data_pipeline.transform import transform
from src.data_pipeline.validate import validate_dataframe
from src.ml_pipeline.evaluate import evaluate, predict_proba
from src.ml_pipeline.register_model import check_promotion_gate
from src.ml_pipeline.responsible_ai.error_analysis import analyze_slices
from src.ml_pipeline.responsible_ai.fairness_metrics import assess_fairness
from src.ml_pipeline.responsible_ai.shap_explainability import compute_shap_values, global_feature_importance
from src.ml_pipeline.train import prepare_xy, temporal_split, train_model

FAST_HYPERPARAMETERS = {
    "num_leaves": 7,
    "learning_rate": 0.1,
    "n_estimators": 25,
    "min_child_samples": 5,
    "feature_fraction": 0.9,
}


def test_full_pipeline_runs_end_to_end(tmp_path: Path) -> None:
    # 1. Ingest -----------------------------------------------------------------
    raw = generate_synthetic_encounters(n_rows=600, start_date=date(2024, 1, 1), seed=123)
    raw_path = tmp_path / "raw" / "encounters.csv"
    write_table(raw, raw_path)

    # 2. Validate -----------------------------------------------------------------
    loaded_raw = read_table(raw_path)
    validation_result = validate_dataframe(loaded_raw)
    assert validation_result["success"] is True

    # 3. Transform ------------------------------------------------------------
    features = transform(loaded_raw)
    features_path = tmp_path / "processed" / "features.parquet"
    write_table(features, features_path)

    # 4. Train ------------------------------------------------------------------
    config = load_config(None)
    config["model"]["hyperparameters"] = FAST_HYPERPARAMETERS

    curated = read_table(features_path)
    train_df, val_df, test_df = temporal_split(curated, train_fraction=0.70, validation_fraction=0.15)

    X_train, y_train = prepare_xy(train_df, algorithm="lightgbm")
    X_val, y_val = prepare_xy(val_df, algorithm="lightgbm")
    model = train_model(
        X_train, y_train, X_val, y_val,
        algorithm="lightgbm",
        hyperparameters=config["model"]["hyperparameters"],
        random_seed=config["model"]["random_seed"],
    )

    model_bundle = {
        "model": model,
        "algorithm": "lightgbm",
        "feature_columns": MODEL_FEATURE_COLUMNS,
        "categorical_columns": CATEGORICAL_COLUMNS,
        "categorical_categories": {c: sorted(train_df[c].unique()) for c in CATEGORICAL_COLUMNS},
        "train_columns": list(X_train.columns),
    }

    output_dir = tmp_path / "outputs"
    output_dir.mkdir()
    model_path = output_dir / "model.pkl"
    joblib.dump(model_bundle, model_path)
    write_table(test_df, output_dir / "test.parquet")

    # 5. Evaluate -----------------------------------------------------------------
    loaded_bundle = joblib.load(model_path)
    loaded_test_df = pd.read_parquet(output_dir / "test.parquet")

    metrics = evaluate(loaded_bundle, loaded_test_df, config)
    metrics_path = output_dir / "metrics.json"
    metrics_path.write_text(json.dumps(metrics, indent=2), encoding="utf-8")

    assert 0.0 <= metrics["roc_auc"] <= 1.0
    assert metrics["n_rows"] == len(loaded_test_df)

    # 6. Responsible AI -------------------------------------------------------------
    threshold = config["evaluation"]["decision_threshold"]
    fairness_report = assess_fairness(loaded_bundle, loaded_test_df, config, threshold)
    fairness_path = output_dir / "responsible_ai" / "fairness_report.json"
    fairness_path.parent.mkdir(parents=True, exist_ok=True)
    fairness_path.write_text(json.dumps(fairness_report, indent=2), encoding="utf-8")

    y_true = loaded_test_df[LABEL_COLUMN].astype(int)
    y_prob = predict_proba(loaded_bundle, loaded_test_df)
    y_pred = pd.Series((y_prob >= threshold).astype(int), index=loaded_test_df.index)

    error_report = analyze_slices(
        loaded_test_df, y_true, y_pred,
        min_slice_size=config.get("responsible_ai", {}).get("error_analysis_min_slice_size", 30),
    )
    assert 0.0 <= error_report["global_error_rate"] <= 1.0

    X_test, _ = prepare_xy(
        loaded_test_df.assign(**{LABEL_COLUMN: loaded_test_df.get(LABEL_COLUMN, 0)}),
        algorithm=loaded_bundle["algorithm"],
        categorical_dtypes=loaded_bundle["categorical_categories"],
    )
    shap_values = compute_shap_values(loaded_bundle, X_test)
    importance = global_feature_importance(shap_values, list(X_test.columns))
    assert len(importance) == X_test.shape[1]

    # 7. Promotion gate ---------------------------------------------------------
    failures = check_promotion_gate(metrics, fairness_report, config)
    assert isinstance(failures, list)

    # All expected artifacts were written to disk.
    assert model_path.exists()
    assert metrics_path.exists()
    assert fairness_path.exists()
