"""Unit tests for src/data_pipeline/transform.py."""

from __future__ import annotations

import numpy as np
import pandas as pd

from src.common.schemas import LABEL_COLUMN
from src.data_pipeline.transform import clean_raw_encounters, transform


def _raw_df_with_duplicates_and_missing_label() -> pd.DataFrame:
    base = {
        "encounter_id": "ENC-1",
        "patient_id": "PAT-1",
        "admit_date": "2024-01-01",
        "discharge_date": "2024-01-05",
        "age": 70,
        "sex": "F",
        "ethnicity": "Group A",
        "insurance_type": "Medicare",
        "admission_type": "Emergency",
        "discharge_disposition": "SNF",
        "length_of_stay": 4,
        "primary_diagnosis_code": "I50.9",
        "comorbidity_count": 3,
        "charlson_index": 4.0,
        "prior_admissions_12mo": 1,
        "prior_ed_visits_12mo": 1,
        "num_medications": 8,
        "bmi": 27.0,
        "systolic_bp": 130.0,
        "glucose_level": 110.0,
        "creatinine": 1.1,
        "readmitted_30d": 1,
    }
    duplicate = dict(base)

    missing_label = dict(base)
    missing_label["encounter_id"] = "ENC-2"
    missing_label["readmitted_30d"] = None

    return pd.DataFrame([base, duplicate, missing_label])


def test_clean_raw_encounters_dedups_and_coerces_dates() -> None:
    raw = _raw_df_with_duplicates_and_missing_label()
    cleaned = clean_raw_encounters(raw)

    # Duplicate ENC-1 row removed, and the row missing readmitted_30d dropped.
    assert len(cleaned) == 1
    assert cleaned.iloc[0]["encounter_id"] == "ENC-1"

    assert pd.api.types.is_datetime64_any_dtype(cleaned["admit_date"])
    assert pd.api.types.is_datetime64_any_dtype(cleaned["discharge_date"])


def test_clean_raw_encounters_passes_through_when_label_absent() -> None:
    raw = _raw_df_with_duplicates_and_missing_label().drop(columns=["readmitted_30d"])
    cleaned = clean_raw_encounters(raw)

    # No label column -> no rows dropped for missing label, only dedup applies.
    assert len(cleaned) == 2


def test_transform_produces_engineered_features(raw_encounters_df: pd.DataFrame) -> None:
    features = transform(raw_encounters_df)

    assert len(features) == raw_encounters_df["encounter_id"].nunique()
    assert "age_band" in features.columns
    assert "los_bucket" in features.columns
    assert LABEL_COLUMN in features.columns
    assert not features[LABEL_COLUMN].isna().any()
    assert set(np.unique(features[LABEL_COLUMN])).issubset({0, 1})
