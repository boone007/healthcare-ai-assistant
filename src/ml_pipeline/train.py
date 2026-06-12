"""Train the readmission-risk model.

Loads the curated feature table, performs a temporal train/validation/test
split, trains a LightGBM (default) or XGBoost classifier per
``configs/train_config.yaml``, and persists the model artifact plus split
datasets for downstream evaluation and responsible AI stages.

Usage:
    python -m src.ml_pipeline.train \\
        --data data/processed/features.parquet \\
        --config configs/train_config.yaml \\
        --output-dir outputs
"""

from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import Any

import joblib
import pandas as pd

from src.common.config import load_config
from src.common.logging_utils import get_logger
from src.common.schemas import CATEGORICAL_COLUMNS, LABEL_COLUMN, MODEL_FEATURE_COLUMNS
from src.common.utils import ensure_dir, set_seed, timer

logger = get_logger(__name__)


def temporal_split(
    df: pd.DataFrame, train_fraction: float, validation_fraction: float
) -> tuple[pd.DataFrame, pd.DataFrame, pd.DataFrame]:
    """Split ``df`` into train/validation/test sets ordered by ``discharge_date``.

    The oldest ``train_fraction`` of rows form the training set, the next
    ``validation_fraction`` form the validation set, and the remainder forms
    the held-out test set. This avoids leaking future information into
    training, per ``docs/ml-design.md`` §3.
    """
    sorted_df = df.sort_values("discharge_date").reset_index(drop=True)
    n = len(sorted_df)

    train_end = int(n * train_fraction)
    val_end = train_end + int(n * validation_fraction)

    train_df = sorted_df.iloc[:train_end]
    val_df = sorted_df.iloc[train_end:val_end]
    test_df = sorted_df.iloc[val_end:]

    logger.info(
        "temporal_split",
        extra={"train_rows": len(train_df), "val_rows": len(val_df), "test_rows": len(test_df)},
    )
    return train_df, val_df, test_df


def prepare_xy(
    df: pd.DataFrame, algorithm: str, categorical_dtypes: dict[str, list[str]] | None = None
) -> tuple[pd.DataFrame, pd.Series]:
    """Split a feature DataFrame into model inputs ``X`` and label ``y``.

    For ``lightgbm``, categorical columns are cast to pandas ``category``
    dtype (LightGBM's native categorical handling). For ``xgboost``,
    categorical columns are one-hot encoded.

    Args:
        df: Feature DataFrame including ``MODEL_FEATURE_COLUMNS`` and
            ``LABEL_COLUMN``.
        algorithm: ``"lightgbm"`` or ``"xgboost"``.
        categorical_dtypes: For ``xgboost``/inference consistency, a mapping
            of categorical column -> sorted list of known categories used to
            build a stable one-hot encoding. If ``None``, categories are
            derived from ``df`` itself (training time).
    """
    X = df[MODEL_FEATURE_COLUMNS].copy()
    y = df[LABEL_COLUMN].astype(int)

    if algorithm == "lightgbm":
        for col in CATEGORICAL_COLUMNS:
            X[col] = X[col].astype("category")
        return X, y

    if algorithm == "xgboost":
        for col in CATEGORICAL_COLUMNS:
            categories = (categorical_dtypes or {}).get(col, sorted(X[col].unique()))
            X[col] = pd.Categorical(X[col], categories=categories)
        X = pd.get_dummies(X, columns=CATEGORICAL_COLUMNS, dummy_na=False)
        return X, y

    raise ValueError(f"Unsupported algorithm: {algorithm}")


@timer
def train_model(
    X_train: pd.DataFrame,
    y_train: pd.Series,
    X_val: pd.DataFrame,
    y_val: pd.Series,
    algorithm: str,
    hyperparameters: dict[str, Any],
    random_seed: int,
):
    """Train a gradient-boosted classifier with early stopping on the validation set."""
    pos_weight = (y_train == 0).sum() / max((y_train == 1).sum(), 1)

    if algorithm == "lightgbm":
        from lightgbm import LGBMClassifier, early_stopping, log_evaluation

        model = LGBMClassifier(
            objective="binary",
            random_state=random_seed,
            scale_pos_weight=pos_weight,
            **hyperparameters,
        )
        model.fit(
            X_train,
            y_train,
            eval_set=[(X_val, y_val)],
            eval_metric="average_precision",
            callbacks=[early_stopping(stopping_rounds=30, verbose=False), log_evaluation(period=0)],
        )
        return model

    if algorithm == "xgboost":
        from xgboost import XGBClassifier

        model = XGBClassifier(
            objective="binary:logistic",
            random_state=random_seed,
            scale_pos_weight=pos_weight,
            eval_metric="aucpr",
            early_stopping_rounds=30,
            **hyperparameters,
        )
        model.fit(X_train, y_train, eval_set=[(X_val, y_val)], verbose=False)
        return model

    raise ValueError(f"Unsupported algorithm: {algorithm}")


def main() -> None:
    parser = argparse.ArgumentParser(description="Train the readmission-risk model.")
    parser.add_argument("--data", required=True, help="Path to curated feature table (.parquet)")
    parser.add_argument("--config", default="configs/train_config.yaml", help="Path to training config YAML")
    parser.add_argument("--output-dir", default="outputs", help="Directory to write model + split artifacts")
    args = parser.parse_args()

    config = load_config(args.config)
    model_cfg = config["model"]
    data_cfg = config["data"]
    set_seed(model_cfg["random_seed"])

    df = pd.read_parquet(args.data)
    train_df, val_df, test_df = temporal_split(
        df, data_cfg["train_fraction"], data_cfg["validation_fraction"]
    )

    algorithm = model_cfg["algorithm"]
    X_train, y_train = prepare_xy(train_df, algorithm)
    X_val, y_val = prepare_xy(
        val_df, algorithm, categorical_dtypes={c: list(X_train[c].cat.categories) for c in CATEGORICAL_COLUMNS}
        if algorithm == "lightgbm"
        else {c: sorted(train_df[c].unique()) for c in CATEGORICAL_COLUMNS},
    )

    model = train_model(
        X_train, y_train, X_val, y_val,
        algorithm=algorithm,
        hyperparameters=model_cfg["hyperparameters"],
        random_seed=model_cfg["random_seed"],
    )

    output_dir = ensure_dir(args.output_dir)
    model_path = output_dir / "model.pkl"
    joblib.dump(
        {
            "model": model,
            "algorithm": algorithm,
            "feature_columns": MODEL_FEATURE_COLUMNS,
            "categorical_columns": CATEGORICAL_COLUMNS,
            "categorical_categories": {c: sorted(train_df[c].unique()) for c in CATEGORICAL_COLUMNS},
            "train_columns": list(X_train.columns),
        },
        model_path,
    )
    logger.info("model_saved", extra={"path": str(model_path), "algorithm": algorithm})

    # Persist splits for evaluate.py and responsible_ai/*
    train_df.to_parquet(output_dir / "train.parquet", index=False)
    val_df.to_parquet(output_dir / "val.parquet", index=False)
    test_df.to_parquet(output_dir / "test.parquet", index=False)

    with open(output_dir / "train_summary.json", "w", encoding="utf-8") as fh:
        json.dump(
            {
                "algorithm": algorithm,
                "hyperparameters": model_cfg["hyperparameters"],
                "rows": {"train": len(train_df), "val": len(val_df), "test": len(test_df)},
                "positive_rate": {
                    "train": float(y_train.mean()),
                    "val": float(y_val.mean()),
                },
            },
            fh,
            indent=2,
        )

    # Best-effort MLflow logging for Azure ML run tracking; safe to skip locally.
    try:
        import mlflow

        with mlflow.start_run(nested=True):
            mlflow.log_params(model_cfg["hyperparameters"])
            mlflow.log_param("algorithm", algorithm)
            mlflow.log_metric("train_rows", len(train_df))
            mlflow.log_metric("val_rows", len(val_df))
    except Exception as exc:  # pragma: no cover - MLflow optional locally
        logger.info("mlflow_logging_skipped", extra={"reason": str(exc)})


if __name__ == "__main__":
    main()
