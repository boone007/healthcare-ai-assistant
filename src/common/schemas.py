"""Canonical data schemas shared across the data pipeline, ML pipeline, and API.

These pydantic models are the single source of truth for field names, types,
and value constraints used by:

- ``src/data_pipeline`` (raw encounter records, validation)
- ``src/ml_pipeline`` (feature schema for training)
- ``src/deployment`` (API request/response contracts, scoring script)
"""

from __future__ import annotations

from datetime import date
from typing import Literal

from pydantic import BaseModel, Field

# ---------------------------------------------------------------------------
# Categorical domains
# ---------------------------------------------------------------------------

Sex = Literal["M", "F", "U"]
AdmissionType = Literal["Elective", "Emergency", "Urgent"]
AgeBand = Literal["<18", "18-39", "40-64", "65-79", "80+"]
LosBucket = Literal["0-2", "3-5", "6-10", "11+"]
RiskTier = Literal["low", "medium", "high"]


# ---------------------------------------------------------------------------
# Raw data pipeline schema
# ---------------------------------------------------------------------------


class RawEncounter(BaseModel):
    """Schema for a single raw inpatient encounter record as ingested.

    This is the contract validated by the Great Expectations suite in
    ``src/data_pipeline/great_expectations/``.
    """

    encounter_id: str
    patient_id: str
    admit_date: date
    discharge_date: date
    age: int = Field(ge=0, le=120)
    sex: Sex
    ethnicity: str
    insurance_type: str
    admission_type: AdmissionType
    discharge_disposition: str
    length_of_stay: int = Field(ge=0, le=365)
    primary_diagnosis_code: str
    comorbidity_count: int = Field(ge=0)
    charlson_index: float = Field(ge=0)
    prior_admissions_12mo: int = Field(ge=0)
    prior_ed_visits_12mo: int = Field(ge=0)
    num_medications: int = Field(ge=0)
    bmi: float = Field(gt=0, lt=100)
    systolic_bp: float = Field(gt=0, lt=300)
    glucose_level: float = Field(gt=0, lt=1000)
    creatinine: float = Field(gt=0, lt=20)
    readmitted_30d: int | None = Field(default=None, ge=0, le=1)


# ---------------------------------------------------------------------------
# Engineered feature schema (output of feature_engineering.py)
# ---------------------------------------------------------------------------


class EngineeredFeatures(BaseModel):
    """Schema for the feature table consumed by training and scoring."""

    encounter_id: str
    discharge_date: date | None = None
    age: int
    age_band: AgeBand
    sex: Sex
    insurance_type: str
    admission_type: AdmissionType
    discharge_disposition: str
    length_of_stay: int
    los_bucket: LosBucket
    comorbidity_count: int
    charlson_index: float
    comorbidity_score: float
    prior_admissions_12mo: int
    prior_ed_visits_12mo: int
    prior_utilization_rate: float
    num_medications: int
    polypharmacy_flag: bool
    bmi: float
    systolic_bp: float
    glucose_level: float
    creatinine: float
    # Optional: present in training data for fairness audits, absent at inference.
    ethnicity: str | None = None
    readmitted_30d: int | None = None


# ---------------------------------------------------------------------------
# API request/response schema
# ---------------------------------------------------------------------------


class ScoringRequest(BaseModel):
    """Request body for ``POST /api/v1/score``."""

    encounter_id: str
    age: int = Field(ge=0, le=120)
    sex: Sex
    insurance_type: str
    admission_type: AdmissionType
    discharge_disposition: str
    length_of_stay: int = Field(ge=0, le=365)
    comorbidity_count: int = Field(ge=0)
    charlson_index: float = Field(ge=0)
    prior_admissions_12mo: int = Field(ge=0)
    prior_ed_visits_12mo: int = Field(ge=0)
    num_medications: int = Field(ge=0)
    bmi: float = Field(gt=0, lt=100)
    systolic_bp: float = Field(gt=0, lt=300)
    glucose_level: float = Field(gt=0, lt=1000)
    creatinine: float = Field(gt=0, lt=20)


class TopFactor(BaseModel):
    """A single SHAP-derived contributing factor for a prediction."""

    feature: str
    shap_value: float


class ScoringResponse(BaseModel):
    """Response body for ``POST /api/v1/score``."""

    encounter_id: str
    model_version: str
    readmission_probability: float = Field(ge=0.0, le=1.0)
    risk_tier: RiskTier
    top_factors: list[TopFactor]
    request_id: str
    scored_at: str


def probability_to_risk_tier(probability: float) -> RiskTier:
    """Map a readmission probability to a clinical risk tier.

    Thresholds mirror ``docs/api-design.md`` §3.1:
      - ``< 0.20``  -> ``low``
      - ``0.20-0.50`` -> ``medium``
      - ``> 0.50``  -> ``high``
    """
    if probability < 0.20:
        return "low"
    if probability <= 0.50:
        return "medium"
    return "high"


# Feature columns used by the model, in a stable order.
MODEL_FEATURE_COLUMNS: list[str] = [
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

# Categorical feature columns requiring encoding before model input.
CATEGORICAL_COLUMNS: list[str] = [
    "age_band",
    "sex",
    "insurance_type",
    "admission_type",
    "discharge_disposition",
    "los_bucket",
]

# Sensitive attributes used for fairness audits (training-time only).
FAIRNESS_SENSITIVE_COLUMNS: list[str] = ["sex", "age_band", "ethnicity"]

LABEL_COLUMN = "readmitted_30d"
