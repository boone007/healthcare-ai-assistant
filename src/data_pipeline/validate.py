"""Data validation using Great Expectations.

Loads the expectation suite defined in
``src/data_pipeline/great_expectations/encounters_suite.json`` and validates
a raw encounter dataset against it. The pipeline halts (non-zero exit code)
if validation fails, preventing low-quality data from reaching feature
engineering and training.

This module uses Great Expectations' lightweight ``PandasDataset`` API
(``great_expectations.dataset``), which validates a DataFrame in-process
without requiring a full Data Context / checkpoint configuration. For larger
deployments, replace this with a Data Context backed by the project's
``great_expectations.yml`` and run as a Checkpoint.

Usage:
    python -m src.data_pipeline.validate --input data/raw/encounters.csv
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

import pandas as pd

from src.common.logging_utils import get_logger
from src.common.utils import read_table, timer

logger = get_logger(__name__)

SUITE_PATH = Path(__file__).parent / "great_expectations" / "encounters_suite.json"


class ValidationError(Exception):
    """Raised when a dataset fails the Great Expectations validation suite."""


@timer
def validate_dataframe(df: pd.DataFrame, suite_path: Path = SUITE_PATH) -> dict:
    """Validate ``df`` against the Great Expectations suite at ``suite_path``.

    Returns:
        The Great Expectations validation result as a dictionary.

    Raises:
        ValidationError: if any expectation fails.
    """
    import great_expectations as ge
    from great_expectations.core.expectation_suite import ExpectationSuite

    with suite_path.open("r", encoding="utf-8") as fh:
        suite_dict = json.load(fh)

    suite = ExpectationSuite(**suite_dict)

    ge_dataset = ge.dataset.PandasDataset(df)
    result = ge_dataset.validate(expectation_suite=suite, result_format="SUMMARY")
    result_dict = result.to_json_dict()

    if not result_dict["success"]:
        failed = [
            r["expectation_config"]["expectation_type"]
            for r in result_dict["results"]
            if not r["success"]
        ]
        logger.error(
            "validation_failed",
            extra={"failed_expectations": failed, "suite": suite.expectation_suite_name},
        )
        raise ValidationError(
            f"Data validation failed against suite '{suite.expectation_suite_name}': "
            f"{len(failed)} expectation(s) failed: {failed}"
        )

    logger.info(
        "validation_passed",
        extra={
            "suite": suite.expectation_suite_name,
            "expectations_evaluated": len(result_dict["results"]),
            "rows": len(df),
        },
    )
    return result_dict


def main() -> None:
    parser = argparse.ArgumentParser(description="Validate a raw encounter dataset with Great Expectations.")
    parser.add_argument("--input", required=True, help="Path to the raw dataset (.csv or .parquet)")
    parser.add_argument("--suite", default=str(SUITE_PATH), help="Path to the GE expectation suite JSON")
    parser.add_argument("--report-out", help="Optional path to write the validation report JSON")
    args = parser.parse_args()

    df = read_table(args.input)

    try:
        result = validate_dataframe(df, suite_path=Path(args.suite))
    except ValidationError as exc:
        logger.error("validation_error", extra={"error": str(exc)})
        sys.exit(1)

    if args.report_out:
        Path(args.report_out).parent.mkdir(parents=True, exist_ok=True)
        with open(args.report_out, "w", encoding="utf-8") as fh:
            json.dump(result, fh, indent=2, default=str)
        logger.info("validation_report_written", extra={"path": args.report_out})


if __name__ == "__main__":
    main()
