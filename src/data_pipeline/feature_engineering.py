"""Feature engineering: derive model-ready features from validated raw encounters.

Each derivation is implemented as a small, pure, testable function so it can
be unit tested independently (see ``tests/unit/test_feature_engineering.py``)
and reused identically at training time and inference time (via
``src/deployment/scoring/score.py``).
"""

from __future__ import annotations

import pandas as pd

from src.common.schemas import AgeBand, LosBucket


def derive_age_band(age: pd.Series) -> pd.Series:
    """Bucket ``age`` into clinically meaningful bands.

    Bands: ``<18``, ``18-39``, ``40-64``, ``65-79``, ``80+``.
    """
    bins = [-1, 17, 39, 64, 79, 200]
    labels: list[AgeBand] = ["<18", "18-39", "40-64", "65-79", "80+"]
    return pd.cut(age, bins=bins, labels=labels).astype(str)


def derive_los_bucket(length_of_stay: pd.Series) -> pd.Series:
    """Bucket ``length_of_stay`` (days) into ``0-2``, ``3-5``, ``6-10``, ``11+``."""
    bins = [-1, 2, 5, 10, 10_000]
    labels: list[LosBucket] = ["0-2", "3-5", "6-10", "11+"]
    return pd.cut(length_of_stay, bins=bins, labels=labels).astype(str)


def derive_comorbidity_score(comorbidity_count: pd.Series, charlson_index: pd.Series) -> pd.Series:
    """Weighted comorbidity score combining raw count and Charlson index.

    A simple weighted blend that emphasizes the clinically-validated
    Charlson index while retaining signal from the raw comorbidity count.
    """
    return (0.4 * comorbidity_count + 0.6 * charlson_index).round(3)


def derive_prior_utilization_rate(
    prior_admissions_12mo: pd.Series, prior_ed_visits_12mo: pd.Series
) -> pd.Series:
    """Monthly utilization rate combining prior admissions and ED visits."""
    return ((prior_admissions_12mo + prior_ed_visits_12mo) / 12.0).round(4)


def derive_polypharmacy_flag(num_medications: pd.Series) -> pd.Series:
    """Flag patients on 5+ medications (clinical definition of polypharmacy)."""
    return num_medications >= 5


def engineer_features(df: pd.DataFrame, *, keep_ethnicity: bool = True) -> pd.DataFrame:
    """Apply all feature derivations to a validated raw encounter DataFrame.

    Args:
        df: A DataFrame conforming to
            :class:`src.common.schemas.RawEncounter`.
        keep_ethnicity: Whether to retain the ``ethnicity`` column in the
            output. Set to ``True`` for training (used in fairness audits)
            and ``False`` for inference-time feature construction, where
            ``ethnicity`` is not collected.

    Returns:
        A DataFrame conforming to
        :class:`src.common.schemas.EngineeredFeatures`.
    """
    out = df.copy()

    out["age_band"] = derive_age_band(out["age"])
    out["los_bucket"] = derive_los_bucket(out["length_of_stay"])
    out["comorbidity_score"] = derive_comorbidity_score(out["comorbidity_count"], out["charlson_index"])
    out["prior_utilization_rate"] = derive_prior_utilization_rate(
        out["prior_admissions_12mo"], out["prior_ed_visits_12mo"]
    )
    out["polypharmacy_flag"] = derive_polypharmacy_flag(out["num_medications"])

    columns = [
        "encounter_id",
        "age",
        "age_band",
        "sex",
        "insurance_type",
        "admission_type",
        "discharge_disposition",
        "length_of_stay",
        "los_bucket",
        "comorbidity_count",
        "charlson_index",
        "comorbidity_score",
        "prior_admissions_12mo",
        "prior_ed_visits_12mo",
        "prior_utilization_rate",
        "num_medications",
        "polypharmacy_flag",
        "bmi",
        "systolic_bp",
        "glucose_level",
        "creatinine",
    ]

    if keep_ethnicity and "ethnicity" in out.columns:
        columns.append("ethnicity")

    if "readmitted_30d" in out.columns:
        columns.append("readmitted_30d")

    if "discharge_date" in out.columns:
        columns.insert(1, "discharge_date")

    return out[columns]
