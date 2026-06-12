"""Fairness assessment across protected attributes.

Computes selection rate, true positive rate (recall), false positive rate,
and false negative rate by group for each sensitive attribute configured in
``configs/train_config.yaml: responsible_ai.fairness_sensitive_columns``
(default: ``sex``, ``age_band``, ``ethnicity``), along with demographic
parity difference and equalized odds difference, using ``fairlearn``.

Results feed the promotion gate in ``register_model.py`` and the fairness
section of ``docs/responsible-ai-report.md``.

Usage:
    python -m src.ml_pipeline.responsible_ai.fairness_metrics \\
        --model-path outputs/model.pkl \\
        --data outputs/test.parquet \\
        --output outputs/responsible_ai/fairness_report.json
"""

from __future__ import annotations

import argparse
import json
from pathlib import Path

import joblib
import pandas as pd

from src.common.config import load_config
from src.common.logging_utils import get_logger
from src.common.schemas import LABEL_COLUMN
from src.ml_pipeline.evaluate import predict_proba

logger = get_logger(__name__)


def compute_group_metrics(
    y_true: pd.Series, y_pred: pd.Series, sensitive_features: pd.Series
) -> dict:
    """Compute per-group selection rate, TPR, FPR, and FNR via ``fairlearn``."""
    from fairlearn.metrics import MetricFrame, false_negative_rate, false_positive_rate, selection_rate, true_positive_rate

    metric_frame = MetricFrame(
        metrics={
            "selection_rate": selection_rate,
            "tpr": true_positive_rate,
            "fpr": false_positive_rate,
            "fnr": false_negative_rate,
        },
        y_true=y_true,
        y_pred=y_pred,
        sensitive_features=sensitive_features,
    )

    by_group = metric_frame.by_group.round(4).to_dict(orient="index")
    overall = metric_frame.overall.round(4).to_dict()

    return {
        "by_group": {str(k): v for k, v in by_group.items()},
        "overall": overall,
        "demographic_parity_difference": round(
            float(metric_frame.difference(method="between_groups")["selection_rate"]), 4
        ),
        "equalized_odds_difference": round(
            float(
                max(
                    metric_frame.difference(method="between_groups")["tpr"],
                    metric_frame.difference(method="between_groups")["fpr"],
                )
            ),
            4,
        ),
    }


def assess_fairness(model_bundle: dict, df: pd.DataFrame, config: dict, threshold: float) -> dict:
    """Run the full fairness assessment across all configured sensitive columns."""
    sensitive_columns = config.get("responsible_ai", {}).get(
        "fairness_sensitive_columns", ["sex", "age_band", "ethnicity"]
    )
    max_eod = config["evaluation"]["promotion_gate"]["max_equalized_odds_difference"]

    y_true = df[LABEL_COLUMN].astype(int)
    y_prob = predict_proba(model_bundle, df)
    y_pred = pd.Series((y_prob >= threshold).astype(int), index=df.index)

    report: dict = {"decision_threshold": threshold, "groups": {}}

    for col in sensitive_columns:
        if col not in df.columns:
            logger.warning("fairness_column_missing", extra={"column": col})
            continue

        group_report = compute_group_metrics(y_true, y_pred, df[col])
        group_report["max_equalized_odds_difference_threshold"] = max_eod
        group_report["passes_equalized_odds_gate"] = (
            group_report["equalized_odds_difference"] <= max_eod
        )
        report["groups"][col] = group_report

        logger.info(
            "fairness_metrics_computed",
            extra={
                "column": col,
                "demographic_parity_difference": group_report["demographic_parity_difference"],
                "equalized_odds_difference": group_report["equalized_odds_difference"],
            },
        )

    return report


def main() -> None:
    parser = argparse.ArgumentParser(description="Compute fairness metrics across sensitive attributes.")
    parser.add_argument("--model-path", required=True, help="Path to the model artifact (.pkl)")
    parser.add_argument("--data", required=True, help="Path to the test feature table (.parquet)")
    parser.add_argument("--config", default="configs/train_config.yaml", help="Path to training config YAML")
    parser.add_argument("--output", default="outputs/responsible_ai/fairness_report.json", help="Output JSON path")
    args = parser.parse_args()

    config = load_config(args.config)
    model_bundle = joblib.load(args.model_path)
    df = pd.read_parquet(args.data)

    threshold = config["evaluation"]["decision_threshold"]
    report = assess_fairness(model_bundle, df, config, threshold)

    output_path = Path(args.output)
    output_path.parent.mkdir(parents=True, exist_ok=True)
    with output_path.open("w", encoding="utf-8") as fh:
        json.dump(report, fh, indent=2)

    logger.info("fairness_report_written", extra={"path": str(output_path)})


if __name__ == "__main__":
    main()
