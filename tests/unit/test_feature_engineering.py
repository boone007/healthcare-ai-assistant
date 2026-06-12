"""Unit tests for src/data_pipeline/feature_engineering.py."""

from __future__ import annotations

import pandas as pd

from src.data_pipeline.feature_engineering import (
    derive_age_band,
    derive_comorbidity_score,
    derive_los_bucket,
    derive_polypharmacy_flag,
    derive_prior_utilization_rate,
    engineer_features,
)


def test_derive_age_band_boundaries() -> None:
    ages = pd.Series([0, 17, 18, 39, 40, 64, 65, 79, 80, 105])
    bands = derive_age_band(ages)
    assert list(bands) == [
        "<18",
        "<18",
        "18-39",
        "18-39",
        "40-64",
        "40-64",
        "65-79",
        "65-79",
        "80+",
        "80+",
    ]


def test_derive_los_bucket_boundaries() -> None:
    los = pd.Series([0, 2, 3, 5, 6, 10, 11, 30])
    buckets = derive_los_bucket(los)
    assert list(buckets) == ["0-2", "0-2", "3-5", "3-5", "6-10", "6-10", "11+", "11+"]


def test_derive_comorbidity_score_weighted_blend() -> None:
    comorbidity_count = pd.Series([0, 2, 10])
    charlson_index = pd.Series([0.0, 1.0, 5.0])
    score = derive_comorbidity_score(comorbidity_count, charlson_index)
    assert list(score) == [0.0, round(0.4 * 2 + 0.6 * 1.0, 3), round(0.4 * 10 + 0.6 * 5.0, 3)]


def test_derive_prior_utilization_rate() -> None:
    prior_admissions = pd.Series([0, 6, 12])
    prior_ed_visits = pd.Series([0, 6, 0])
    rate = derive_prior_utilization_rate(prior_admissions, prior_ed_visits)
    assert list(rate) == [0.0, 1.0, 1.0]


def test_derive_polypharmacy_flag_threshold() -> None:
    num_medications = pd.Series([0, 4, 5, 6])
    flags = derive_polypharmacy_flag(num_medications)
    assert list(flags) == [False, False, True, True]


def _minimal_raw_df() -> pd.DataFrame:
    return pd.DataFrame(
        {
            "encounter_id": ["ENC-1", "ENC-2"],
            "discharge_date": pd.to_datetime(["2024-01-05", "2024-01-10"]),
            "age": [70, 30],
            "sex": ["F", "M"],
            "ethnicity": ["Group A", "Group B"],
            "insurance_type": ["Medicare", "Commercial"],
            "admission_type": ["Emergency", "Elective"],
            "discharge_disposition": ["SNF", "Home"],
            "length_of_stay": [6, 2],
            "comorbidity_count": [4, 0],
            "charlson_index": [5.0, 0.0],
            "prior_admissions_12mo": [2, 0],
            "prior_ed_visits_12mo": [3, 0],
            "num_medications": [12, 1],
            "bmi": [29.4, 22.0],
            "systolic_bp": [138.0, 118.0],
            "glucose_level": [156.0, 90.0],
            "creatinine": [1.3, 0.8],
            "readmitted_30d": [1, 0],
        }
    )


def test_engineer_features_includes_derived_and_optional_columns() -> None:
    raw = _minimal_raw_df()
    out = engineer_features(raw, keep_ethnicity=True)

    for derived in ["age_band", "los_bucket", "comorbidity_score", "prior_utilization_rate", "polypharmacy_flag"]:
        assert derived in out.columns

    # Optional columns retained when present in the input.
    assert "discharge_date" in out.columns
    assert "ethnicity" in out.columns
    assert "readmitted_30d" in out.columns

    assert out.loc[0, "age_band"] == "65-79"
    assert out.loc[0, "los_bucket"] == "6-10"
    assert bool(out.loc[0, "polypharmacy_flag"]) is True


def test_engineer_features_drops_ethnicity_when_requested() -> None:
    raw = _minimal_raw_df()
    out = engineer_features(raw, keep_ethnicity=False)
    assert "ethnicity" not in out.columns
    # Other optional columns are unaffected.
    assert "discharge_date" in out.columns
    assert "readmitted_30d" in out.columns


def test_engineer_features_handles_missing_discharge_date() -> None:
    raw = _minimal_raw_df().drop(columns=["discharge_date"])
    out = engineer_features(raw, keep_ethnicity=True)
    assert "discharge_date" not in out.columns
