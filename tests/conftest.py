"""Shared pytest fixtures for unit, integration, and performance tests.

Fixtures here generate a small synthetic dataset and train a lightweight
LightGBM model so downstream tests (evaluation, responsible AI, scoring)
can exercise real model objects without depending on external data or a
full-scale training run.
"""

from __future__ import annotations

from datetime import date

import pandas as pd
import pytest

from src.common.schemas import CATEGORICAL_COLUMNS, MODEL_FEATURE_COLUMNS
from src.data_pipeline.ingest import generate_synthetic_encounters
from src.data_pipeline.transform import transform
from src.ml_pipeline.train import prepare_xy, temporal_split, train_model

# Small hyperparameters so model training is fast enough for the test suite.
FAST_HYPERPARAMETERS = {
    "num_leaves": 7,
    "learning_rate": 0.1,
    "n_estimators": 25,
    "min_child_samples": 5,
    "feature_fraction": 0.9,
}


@pytest.fixture(scope="session")
def raw_encounters_df() -> pd.DataFrame:
    """A small, deterministic batch of synthetic raw encounters."""
    return generate_synthetic_encounters(n_rows=600, start_date=date(2024, 1, 1), seed=7)


@pytest.fixture(scope="session")
def engineered_df(raw_encounters_df: pd.DataFrame) -> pd.DataFrame:
    """The curated feature table derived from ``raw_encounters_df``."""
    return transform(raw_encounters_df)


@pytest.fixture(scope="session")
def trained_artifacts(engineered_df: pd.DataFrame):
    """A trained LightGBM model bundle plus its train/val/test splits.

    Mirrors the artifact structure written by ``src/ml_pipeline/train.py``.
    """
    train_df, val_df, test_df = temporal_split(engineered_df, train_fraction=0.7, validation_fraction=0.15)

    X_train, y_train = prepare_xy(train_df, algorithm="lightgbm")
    X_val, y_val = prepare_xy(val_df, algorithm="lightgbm")

    model = train_model(
        X_train,
        y_train,
        X_val,
        y_val,
        algorithm="lightgbm",
        hyperparameters=FAST_HYPERPARAMETERS,
        random_seed=42,
    )

    model_bundle = {
        "model": model,
        "algorithm": "lightgbm",
        "feature_columns": MODEL_FEATURE_COLUMNS,
        "categorical_columns": CATEGORICAL_COLUMNS,
        "categorical_categories": {c: sorted(train_df[c].unique()) for c in CATEGORICAL_COLUMNS},
        "train_columns": list(X_train.columns),
    }

    return {
        "model_bundle": model_bundle,
        "train_df": train_df,
        "val_df": val_df,
        "test_df": test_df,
    }


@pytest.fixture(scope="session")
def model_bundle(trained_artifacts: dict) -> dict:
    return trained_artifacts["model_bundle"]


@pytest.fixture(scope="session")
def test_df(trained_artifacts: dict) -> pd.DataFrame:
    return trained_artifacts["test_df"]
