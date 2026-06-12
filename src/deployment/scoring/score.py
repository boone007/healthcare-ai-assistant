"""Scoring script for the AML Managed Online Endpoint.

Implements the standard ``init()`` / ``run()`` entry points expected by Azure
ML's managed online deployments (see
``src/deployment/aml_endpoint/deployment.yml``).

- ``init()`` loads the registered model bundle (produced by
  ``src/ml_pipeline/train.py``) and a SHAP explainer once per instance.
- ``run()`` accepts a JSON request matching
  :class:`src.common.schemas.ScoringRequest` (or a batch thereof), applies
  the same feature engineering used at training time, and returns
  :class:`src.common.schemas.ScoringResponse`-shaped JSON including the
  top-3 SHAP contributing factors.
"""

from __future__ import annotations

import json
import os
import uuid
from datetime import datetime, timezone

import joblib
import pandas as pd

from src.common.logging_utils import get_logger
from src.common.schemas import (
    CATEGORICAL_COLUMNS,
    MODEL_FEATURE_COLUMNS,
    probability_to_risk_tier,
)
from src.data_pipeline.feature_engineering import engineer_features
from src.ml_pipeline.responsible_ai.shap_explainability import top_factors_for_row

logger = get_logger(__name__)

# Populated by init()
_model_bundle: dict | None = None
_explainer = None
_model_version: str = "unknown"


def init() -> None:
    """Load the model bundle and construct a SHAP explainer.

    ``AZUREML_MODEL_DIR`` is set by the AML runtime to the mounted model
    directory; ``MODEL_VERSION`` is set via deployment environment variables
    for inclusion in responses.
    """
    global _model_bundle, _explainer, _model_version

    model_dir = os.environ.get("AZUREML_MODEL_DIR", "outputs")
    model_path = os.path.join(model_dir, "model.pkl")

    _model_bundle = joblib.load(model_path)
    _model_version = os.environ.get("MODEL_VERSION", "readmission-risk-model:latest")

    try:
        import shap

        _explainer = shap.TreeExplainer(_model_bundle["model"])
    except Exception as exc:  # pragma: no cover - explainability is best-effort
        logger.warning("shap_explainer_init_failed", extra={"error": str(exc)})
        _explainer = None

    logger.info("init_complete", extra={"model_version": _model_version, "algorithm": _model_bundle["algorithm"]})


def _prepare_inference_frame(records: list[dict]) -> pd.DataFrame:
    """Run the shared feature-engineering pipeline on raw scoring requests."""
    raw_df = pd.DataFrame.from_records(records)

    # ethnicity is optional at inference time (see docs/ml-design.md §8)
    if "ethnicity" not in raw_df.columns:
        raw_df["ethnicity"] = None

    features = engineer_features(raw_df, keep_ethnicity=False)
    return features


def _build_model_input(features: pd.DataFrame) -> pd.DataFrame:
    """Cast feature columns to the dtypes the model was trained with."""
    X = features[MODEL_FEATURE_COLUMNS].copy()
    algorithm = _model_bundle["algorithm"]
    categories = _model_bundle["categorical_categories"]

    if algorithm == "lightgbm":
        for col in CATEGORICAL_COLUMNS:
            X[col] = pd.Categorical(X[col], categories=categories[col])
        return X

    if algorithm == "xgboost":
        for col in CATEGORICAL_COLUMNS:
            X[col] = pd.Categorical(X[col], categories=categories[col])
        X = pd.get_dummies(X, columns=CATEGORICAL_COLUMNS, dummy_na=False)
        train_columns = _model_bundle.get("train_columns")
        if train_columns is not None:
            X = X.reindex(columns=train_columns, fill_value=0)
        return X

    raise ValueError(f"Unsupported algorithm: {algorithm}")


def run(raw_data: str) -> str:
    """Score one or more encounters.

    Args:
        raw_data: JSON string. Either a single
            :class:`~src.common.schemas.ScoringRequest`-shaped object, or
            ``{"data": [<request>, ...]}`` for a batch.

    Returns:
        JSON string: a single
        :class:`~src.common.schemas.ScoringResponse`-shaped object, or
        ``{"results": [<response>, ...]}`` for a batch.
    """
    payload = json.loads(raw_data)
    records = payload["data"] if isinstance(payload, dict) and "data" in payload else [payload]
    is_batch = isinstance(payload, dict) and "data" in payload

    features = _prepare_inference_frame(records)
    X = _build_model_input(features)

    probabilities = _model_bundle["model"].predict_proba(X)[:, 1]

    shap_values = None
    if _explainer is not None:
        try:
            sv = _explainer.shap_values(X)
            shap_values = sv[1] if isinstance(sv, list) else sv
        except Exception as exc:  # pragma: no cover - explainability is best-effort
            logger.warning("shap_inference_failed", extra={"error": str(exc)})

    scored_at = datetime.now(timezone.utc).isoformat()
    results = []
    for i, record in enumerate(records):
        probability = float(probabilities[i])
        top_factors = (
            top_factors_for_row(shap_values[i], list(X.columns), top_n=3) if shap_values is not None else []
        )
        results.append(
            {
                "encounter_id": record.get("encounter_id", f"unknown-{i}"),
                "model_version": _model_version,
                "readmission_probability": round(probability, 4),
                "risk_tier": probability_to_risk_tier(probability),
                "top_factors": top_factors,
                "request_id": str(uuid.uuid4()),
                "scored_at": scored_at,
            }
        )

    return json.dumps({"results": results} if is_batch else results[0])
