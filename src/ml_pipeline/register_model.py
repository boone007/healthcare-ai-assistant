"""Register a trained model in the Azure ML Model Registry.

Enforces the promotion gate defined in ``configs/train_config.yaml:
evaluation.promotion_gate`` before registering:

- ``roc_auc >= min_roc_auc``
- ``pr_auc >= min_pr_auc``
- ``brier_score <= max_brier_score``
- ``equalized_odds_difference <= max_equalized_odds_difference`` for the
  ``sex`` and ``ethnicity`` sensitive attributes (the ``age_band`` disparity
  is a documented, accepted exception — see
  ``docs/responsible-ai-report.md`` §3.2 and §5).

On success, registers the model artifact with lineage tags (``git_sha``,
``training_run_id``, ``data_version``) and attaches the metrics and
responsible AI reports as registration properties.

Usage:
    python -m src.ml_pipeline.register_model \\
        --model-path outputs/model.pkl \\
        --metrics outputs/metrics.json \\
        --fairness-report outputs/responsible_ai/fairness_report.json \\
        --model-name readmission-risk-model \\
        --subscription-id <sub-id> --resource-group rg-hcai-dev --workspace-name mlw-hcai-dev
"""

from __future__ import annotations

import argparse
import json
import os
import sys
from pathlib import Path

from src.common.config import load_config
from src.common.logging_utils import get_logger

logger = get_logger(__name__)

# Sensitive attributes for which the equalized-odds gate is strictly enforced.
ENFORCED_FAIRNESS_COLUMNS = ["sex", "ethnicity"]


class PromotionGateError(Exception):
    """Raised when a model fails the promotion gate and must not be registered."""


def check_promotion_gate(metrics: dict, fairness_report: dict, config: dict) -> list[str]:
    """Evaluate the promotion gate; returns a list of human-readable failure reasons.

    An empty list means the model passes and may be registered.
    """
    gate = config["evaluation"]["promotion_gate"]
    failures: list[str] = []

    if metrics["roc_auc"] < gate["min_roc_auc"]:
        failures.append(f"roc_auc {metrics['roc_auc']} < required {gate['min_roc_auc']}")

    if metrics["pr_auc"] < gate["min_pr_auc"]:
        failures.append(f"pr_auc {metrics['pr_auc']} < required {gate['min_pr_auc']}")

    if metrics["brier_score"] > gate["max_brier_score"]:
        failures.append(f"brier_score {metrics['brier_score']} > allowed {gate['max_brier_score']}")

    max_eod = gate["max_equalized_odds_difference"]
    for col in ENFORCED_FAIRNESS_COLUMNS:
        group_report = fairness_report.get("groups", {}).get(col)
        if group_report is None:
            logger.warning("fairness_group_missing_from_report", extra={"column": col})
            continue
        eod = group_report["equalized_odds_difference"]
        if eod > max_eod:
            failures.append(f"equalized_odds_difference[{col}] {eod} > allowed {max_eod}")

    return failures


def register(
    model_path: str,
    model_name: str,
    metrics: dict,
    fairness_report: dict,
    subscription_id: str,
    resource_group: str,
    workspace_name: str,
    git_sha: str,
    training_run_id: str,
    data_version: str,
):
    """Register the model artifact in the AML Model Registry with lineage tags."""
    from azure.ai.ml import MLClient
    from azure.ai.ml.constants import AssetTypes
    from azure.ai.ml.entities import Model
    from azure.identity import DefaultAzureCredential

    ml_client = MLClient(
        DefaultAzureCredential(),
        subscription_id=subscription_id,
        resource_group_name=resource_group,
        workspace_name=workspace_name,
    )

    model = Model(
        path=model_path,
        name=model_name,
        type=AssetTypes.CUSTOM_MODEL,
        description="Gradient-boosted classifier predicting 30-day hospital readmission risk.",
        tags={
            "git_sha": git_sha,
            "training_run_id": training_run_id,
            "data_version": data_version,
            "roc_auc": str(metrics["roc_auc"]),
            "pr_auc": str(metrics["pr_auc"]),
            "brier_score": str(metrics["brier_score"]),
        },
        properties={
            "metrics_json": json.dumps(metrics),
            "fairness_report_json": json.dumps(fairness_report),
        },
    )

    registered = ml_client.models.create_or_update(model)
    logger.info(
        "model_registered",
        extra={"name": registered.name, "version": registered.version, "id": registered.id},
    )
    return registered


def main() -> None:
    parser = argparse.ArgumentParser(description="Register a model in the Azure ML Model Registry.")
    parser.add_argument("--model-path", required=True, help="Path to the model artifact (.pkl or directory)")
    parser.add_argument("--metrics", default="outputs/metrics.json", help="Path to evaluate.py metrics JSON")
    parser.add_argument(
        "--fairness-report",
        default="outputs/responsible_ai/fairness_report.json",
        help="Path to fairness_metrics.py report JSON",
    )
    parser.add_argument("--config", default="configs/train_config.yaml")
    parser.add_argument("--model-name", default="readmission-risk-model")
    parser.add_argument("--subscription-id", default=os.environ.get("AZURE_SUBSCRIPTION_ID", ""))
    parser.add_argument("--resource-group", default=os.environ.get("AZURE_RESOURCE_GROUP", ""))
    parser.add_argument("--workspace-name", default=os.environ.get("AZURE_ML_WORKSPACE", ""))
    parser.add_argument("--git-sha", default=os.environ.get("GIT_SHA", "unknown"))
    parser.add_argument("--training-run-id", default=os.environ.get("AML_RUN_ID", "local"))
    parser.add_argument("--data-version", default=os.environ.get("DATA_VERSION", "unknown"))
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Evaluate the promotion gate only; do not register the model in AML.",
    )
    args = parser.parse_args()

    config = load_config(args.config)
    metrics = json.loads(Path(args.metrics).read_text(encoding="utf-8"))
    fairness_report = json.loads(Path(args.fairness_report).read_text(encoding="utf-8"))

    failures = check_promotion_gate(metrics, fairness_report, config)
    if failures:
        logger.error("promotion_gate_failed", extra={"failures": failures})
        for reason in failures:
            print(f"FAIL: {reason}", file=sys.stderr)
        raise PromotionGateError(f"Model failed promotion gate: {failures}")

    logger.info("promotion_gate_passed")

    if args.dry_run:
        logger.info("dry_run_complete", extra={"model_name": args.model_name})
        return

    register(
        model_path=args.model_path,
        model_name=args.model_name,
        metrics=metrics,
        fairness_report=fairness_report,
        subscription_id=args.subscription_id,
        resource_group=args.resource_group,
        workspace_name=args.workspace_name,
        git_sha=args.git_sha,
        training_run_id=args.training_run_id,
        data_version=args.data_version,
    )


if __name__ == "__main__":
    main()
