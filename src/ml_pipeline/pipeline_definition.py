"""Azure ML pipeline definition (Python SDK v2).

Defines the end-to-end training pipeline as a sequence of ``command``
components:

    validate -> transform -> train -> evaluate -> responsible_ai -> register

Each step shells out to the corresponding module under ``src/`` so the exact
same code runs locally (via the CLI entry points in each module) and inside
the AML pipeline.

This module exposes :func:`build_pipeline`, which returns a
``@pipeline``-decorated function ready to be called and submitted via
``ml_client.jobs.create_or_update(pipeline_job)``. The declarative equivalent
is provided in ``pipeline_definition.yml`` for ``az ml job create -f``.

Usage:
    python -m src.ml_pipeline.pipeline_definition \\
        --subscription-id <sub-id> --resource-group rg-hcai-dev \\
        --workspace-name mlw-hcai-dev --compute cpu-cluster-dev \\
        --raw-data-asset azureml:encounters_raw:1
"""

from __future__ import annotations

import argparse

from src.common.logging_utils import get_logger

logger = get_logger(__name__)

ENVIRONMENT = "hcai-training-env:latest"
CODE_DIR = "../../.."  # repository root relative to this file, for `code=` references


def build_pipeline(compute: str, environment: str = ENVIRONMENT):
    """Construct the AML training pipeline as a ``@pipeline``-decorated callable.

    Args:
        compute: Name of the AML compute cluster, e.g. ``cpu-cluster-dev``.
        environment: AML environment reference (``name:version``) providing
            the dependencies in ``requirements.txt``.

    Returns:
        A callable decorated with ``@pipeline`` that accepts a ``raw_data``
        input and returns named outputs for the model, metrics, and
        responsible AI reports.
    """
    from azure.ai.ml import Input, Output, command, dsl

    validate_step = command(
        name="validate_data",
        display_name="Validate raw encounters (Great Expectations)",
        code=CODE_DIR,
        command=(
            "python -m src.data_pipeline.validate "
            "--input ${{inputs.raw_data}} "
            "--report-out ${{outputs.validation_report}}/report.json"
        ),
        inputs={"raw_data": Input(type="uri_file")},
        outputs={"validation_report": Output(type="uri_folder")},
        environment=environment,
        compute=compute,
    )

    transform_step = command(
        name="transform_features",
        display_name="Feature engineering",
        code=CODE_DIR,
        command=(
            "python -m src.data_pipeline.transform "
            "--input ${{inputs.raw_data}} "
            "--output ${{outputs.features}}/features.parquet"
        ),
        inputs={"raw_data": Input(type="uri_file")},
        outputs={"features": Output(type="uri_folder")},
        environment=environment,
        compute=compute,
    )

    train_step = command(
        name="train_model",
        display_name="Train readmission-risk model",
        code=CODE_DIR,
        command=(
            "python -m src.ml_pipeline.train "
            "--data ${{inputs.features}}/features.parquet "
            "--config ${{inputs.config_path}} "
            "--output-dir ${{outputs.model_dir}}"
        ),
        inputs={"features": Input(type="uri_folder"), "config_path": "configs/train_config.yaml"},
        outputs={"model_dir": Output(type="uri_folder")},
        environment=environment,
        compute=compute,
    )

    evaluate_step = command(
        name="evaluate_model",
        display_name="Evaluate model (AUC, PR, calibration)",
        code=CODE_DIR,
        command=(
            "python -m src.ml_pipeline.evaluate "
            "--model-path ${{inputs.model_dir}}/model.pkl "
            "--data ${{inputs.model_dir}}/test.parquet "
            "--config ${{inputs.config_path}} "
            "--output ${{outputs.metrics_dir}}/metrics.json"
        ),
        inputs={"model_dir": Input(type="uri_folder"), "config_path": "configs/train_config.yaml"},
        outputs={"metrics_dir": Output(type="uri_folder")},
        environment=environment,
        compute=compute,
    )

    shap_step = command(
        name="shap_explainability",
        display_name="Responsible AI: SHAP explainability",
        code=CODE_DIR,
        command=(
            "python -m src.ml_pipeline.responsible_ai.shap_explainability "
            "--model-path ${{inputs.model_dir}}/model.pkl "
            "--data ${{inputs.model_dir}}/test.parquet "
            "--config ${{inputs.config_path}} "
            "--output ${{outputs.rai_dir}}/shap_report.json"
        ),
        inputs={"model_dir": Input(type="uri_folder"), "config_path": "configs/train_config.yaml"},
        outputs={"rai_dir": Output(type="uri_folder")},
        environment=environment,
        compute=compute,
    )

    fairness_step = command(
        name="fairness_metrics",
        display_name="Responsible AI: fairness metrics",
        code=CODE_DIR,
        command=(
            "python -m src.ml_pipeline.responsible_ai.fairness_metrics "
            "--model-path ${{inputs.model_dir}}/model.pkl "
            "--data ${{inputs.model_dir}}/test.parquet "
            "--config ${{inputs.config_path}} "
            "--output ${{outputs.rai_dir}}/fairness_report.json"
        ),
        inputs={"model_dir": Input(type="uri_folder"), "config_path": "configs/train_config.yaml"},
        outputs={"rai_dir": Output(type="uri_folder")},
        environment=environment,
        compute=compute,
    )

    error_analysis_step = command(
        name="error_analysis",
        display_name="Responsible AI: error/slice analysis",
        code=CODE_DIR,
        command=(
            "python -m src.ml_pipeline.responsible_ai.error_analysis "
            "--model-path ${{inputs.model_dir}}/model.pkl "
            "--data ${{inputs.model_dir}}/test.parquet "
            "--config ${{inputs.config_path}} "
            "--output ${{outputs.rai_dir}}/error_analysis.json"
        ),
        inputs={"model_dir": Input(type="uri_folder"), "config_path": "configs/train_config.yaml"},
        outputs={"rai_dir": Output(type="uri_folder")},
        environment=environment,
        compute=compute,
    )

    register_step = command(
        name="register_model",
        display_name="Register model (promotion gate)",
        code=CODE_DIR,
        command=(
            "python -m src.ml_pipeline.register_model "
            "--model-path ${{inputs.model_dir}}/model.pkl "
            "--metrics ${{inputs.metrics_dir}}/metrics.json "
            "--fairness-report ${{inputs.rai_dir}}/fairness_report.json "
            "--config ${{inputs.config_path}} "
            "--model-name readmission-risk-model"
        ),
        inputs={
            "model_dir": Input(type="uri_folder"),
            "metrics_dir": Input(type="uri_folder"),
            "rai_dir": Input(type="uri_folder"),
            "config_path": "configs/train_config.yaml",
        },
        environment=environment,
        compute=compute,
    )

    @dsl.pipeline(
        name="hcai_readmission_training_pipeline",
        display_name="Healthcare AI Assistant - Readmission Risk Training Pipeline",
        description="Validate -> transform -> train -> evaluate -> responsible AI -> register",
    )
    def pipeline(raw_data: Input):
        validate_job = validate_step(raw_data=raw_data)
        transform_job = transform_step(raw_data=raw_data)
        train_job = train_step(features=transform_job.outputs.features)
        evaluate_job = evaluate_step(model_dir=train_job.outputs.model_dir)
        shap_job = shap_step(model_dir=train_job.outputs.model_dir)
        fairness_job = fairness_step(model_dir=train_job.outputs.model_dir)
        error_job = error_analysis_step(model_dir=train_job.outputs.model_dir)
        register_step(
            model_dir=train_job.outputs.model_dir,
            metrics_dir=evaluate_job.outputs.metrics_dir,
            rai_dir=fairness_job.outputs.rai_dir,
        )

        return {
            "validation_report": validate_job.outputs.validation_report,
            "model_dir": train_job.outputs.model_dir,
            "metrics_dir": evaluate_job.outputs.metrics_dir,
            "shap_dir": shap_job.outputs.rai_dir,
            "fairness_dir": fairness_job.outputs.rai_dir,
            "error_analysis_dir": error_job.outputs.rai_dir,
        }

    return pipeline


def main() -> None:
    parser = argparse.ArgumentParser(description="Submit the AML training pipeline.")
    parser.add_argument("--subscription-id", required=True)
    parser.add_argument("--resource-group", required=True)
    parser.add_argument("--workspace-name", required=True)
    parser.add_argument("--compute", default="cpu-cluster-dev")
    parser.add_argument("--raw-data-asset", required=True, help="AML data asset URI, e.g. azureml:encounters_raw:1")
    args = parser.parse_args()

    from azure.ai.ml import Input, MLClient
    from azure.identity import DefaultAzureCredential

    ml_client = MLClient(
        DefaultAzureCredential(),
        subscription_id=args.subscription_id,
        resource_group_name=args.resource_group,
        workspace_name=args.workspace_name,
    )

    pipeline_fn = build_pipeline(compute=args.compute)
    pipeline_job = pipeline_fn(raw_data=Input(type="uri_file", path=args.raw_data_asset))

    submitted = ml_client.jobs.create_or_update(pipeline_job)
    logger.info("pipeline_submitted", extra={"job_name": submitted.name, "studio_url": submitted.studio_url})


if __name__ == "__main__":
    main()
