"""Unit tests for src/data_pipeline/validate.py."""

from __future__ import annotations

import pandas as pd
import pytest

from src.data_pipeline.validate import ValidationError, validate_dataframe


def test_validate_dataframe_passes_for_synthetic_data(raw_encounters_df: pd.DataFrame) -> None:
    result = validate_dataframe(raw_encounters_df)
    assert result["success"] is True


def test_validate_dataframe_fails_on_invalid_age(raw_encounters_df: pd.DataFrame) -> None:
    invalid = raw_encounters_df.copy()
    invalid.loc[0, "age"] = -5  # violates expect_column_values_to_be_between for "age"

    with pytest.raises(ValidationError):
        validate_dataframe(invalid)


def test_validate_dataframe_fails_on_invalid_sex_value(raw_encounters_df: pd.DataFrame) -> None:
    invalid = raw_encounters_df.copy()
    invalid.loc[0, "sex"] = "X"  # not in {"M", "F", "U"}

    with pytest.raises(ValidationError):
        validate_dataframe(invalid)
