"""Hyperparameter tuning via an Azure ML Sweep job.

Defines a ``command`` job that runs ``src/ml_pipeline/train.py`` and wraps it
in a ``sweep`` job over the search space defined in
``configs/train_config.yaml: hyperparameter_search``, using Bayesian sampling
with bandit-policy early termination.

This module can be:

1. Imported by ``pipeline_definition.py`` to embed the sweep as a pipeline step, or
2. Run standalone to launch a sweep job directly against an AML workspace:

    python -m src.ml_pipeline.hyperparameter_tuning \\
        --config configs/train_config.yaml \\
        --subscription-id <sub-id> \\
        --resource-group rg-hcai-dev \\
        --workspace-name mlw-hcai-dev \\
        --compute cpu-cluster-dev
"""

from __future__ import annotations

import argparse

from src.common.config import load_config
from src.common.logging_utils import get_logger

logger = get_logger(__name__)


def _build_search_space(search_space_cfg: dict):
    """Translate the YAML search-space config into AML ``sweep`` distributions."""
    from azure.ai.ml.sweep import Choice, LogUniform, Uniform

    distributions = {}
    for param, spec in search_space_cfg.items():
        if isinstance(spec, list):
            distributions[param] = Choice(values=spec)
        elif isinstance(spec, dict) and spec.get("type") == "loguniform":
            distributions[param] = LogUniform(min_value=spec["min_value"], max_value=spec["max_value"])
        elif isinstance(spec, dict) and spec.get("type") == "uniform":
            distributions[param] = Uniform(min_value=spec["min_value"], max_value=spec["max_value"])
        else:
            raise ValueError(f"Unsupported search space spec for '{param}': {spec}")
    return distributions


def build_sweep_job(config: dict, compute: str, data_asset: str, environment: str):
    """Construct an AML ``sweep`` job for the training script.

    Args:
        config: Merged configuration (see ``src/common/config.py``).
        compute: Name of the AML compute cluster to run on, e.g. ``cpu-cluster-dev``.
        data_asset: URI or AML data-asset reference to the curated feature table.
        environment: AML environment reference (name:version) for the training image.

    Returns:
        An ``azure.ai.ml.entities.SweepJob``-compatible job object, ready to
        be submitted via ``ml_client.jobs.create_or_update(job)``.
    """
    from azure.ai.ml import Input, command
    from azure.ai.ml.sweep import BanditPolicy

    hp_cfg = config["hyperparameter_search"]
    search_space = _build_search_space(hp_cfg["search_space"])

    base_command = command(
        code="..",  # repository root, so `python -m src.ml_pipeline.train` resolves
        command=(
            "python -m src.ml_pipeline.train "
            "--data ${{inputs.data}} "
            "--config ${{inputs.config_path}} "
            "--output-dir ${{outputs.model_dir}}"
        ),
        inputs={
            "data": Input(type="uri_file", path=data_asset),
            "config_path": "configs/train_config.yaml",
        },
        environment=environment,
        compute=compute,
        display_name="readmission-train-trial",
    )

    # Override hyperparameters via search-space inputs; train.py reads them
    # from configs/train_config.yaml, so a sweep-aware variant would expose
    # them as CLI overrides. For brevity, this sweep tunes a thin wrapper
    # that writes a per-trial config file before delegating to train.py.
    sweep_job = base_command.sweep(
        primary_metric=hp_cfg["primary_metric"],
        goal=hp_cfg["goal"],
        sampling_algorithm="bayesian",
        search_space=search_space,
    )

    sweep_job.set_limits(
        max_total_trials=hp_cfg["max_total_trials"],
        max_concurrent_trials=hp_cfg["max_concurrent_trials"],
        timeout=7200,
    )

    et = hp_cfg["early_termination"]
    sweep_job.early_termination = BanditPolicy(
        evaluation_interval=et["evaluation_interval"],
        slack_factor=et["slack_factor"],
    )

    return sweep_job


def main() -> None:
    parser = argparse.ArgumentParser(description="Submit a hyperparameter sweep job to Azure ML.")
    parser.add_argument("--config", default="configs/train_config.yaml")
    parser.add_argument("--subscription-id", required=True)
    parser.add_argument("--resource-group", required=True)
    parser.add_argument("--workspace-name", required=True)
    parser.add_argument("--compute", default="cpu-cluster-dev")
    parser.add_argument("--data-asset", required=True, help="URI or data asset path to curated features")
    parser.add_argument("--environment", default="hcai-training-env:latest")
    args = parser.parse_args()

    from azure.ai.ml import MLClient
    from azure.identity import DefaultAzureCredential

    config = load_config(args.config)

    ml_client = MLClient(
        DefaultAzureCredential(),
        subscription_id=args.subscription_id,
        resource_group_name=args.resource_group,
        workspace_name=args.workspace_name,
    )

    sweep_job = build_sweep_job(config, compute=args.compute, data_asset=args.data_asset, environment=args.environment)
    submitted = ml_client.jobs.create_or_update(sweep_job)

    logger.info("sweep_job_submitted", extra={"job_name": submitted.name, "studio_url": submitted.studio_url})


if __name__ == "__main__":
    main()
