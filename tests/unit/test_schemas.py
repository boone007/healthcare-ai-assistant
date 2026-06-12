"""Unit tests for src/common/schemas.py."""

from __future__ import annotations

import pytest
from pydantic import ValidationError

from src.common.schemas import ScoringRequest, probability_to_risk_tier


@pytest.mark.parametrize(
    ("probability", "expected_tier"),
    [
        (0.0, "low"),
        (0.19, "low"),
        (0.1999, "low"),
        (0.20, "medium"),
        (0.35, "medium"),
        (0.50, "medium"),
        (0.5001, "high"),
        (1.0, "high"),
    ],
)
def test_probability_to_risk_tier(probability: float, expected_tier: str) -> None:
    assert probability_to_risk_tier(probability) == expected_tier


def test_scoring_request_accepts_valid_payload() -> None:
    request = ScoringRequest(
        encounter_id="ENC-100000",
        age=74,
        sex="F",
        insurance_type="Medicare",
        admission_type="Emergency",
        discharge_disposition="SNF",
        length_of_stay=6,
        comorbidity_count=4,
        charlson_index=5.0,
        prior_admissions_12mo=2,
        prior_ed_visits_12mo=3,
        num_medications=12,
        bmi=29.4,
        systolic_bp=138.0,
        glucose_level=156.0,
        creatinine=1.3,
    )
    assert request.encounter_id == "ENC-100000"
    assert request.sex == "F"


def test_scoring_request_rejects_invalid_age() -> None:
    with pytest.raises(ValidationError):
        ScoringRequest(
            encounter_id="ENC-100001",
            age=150,  # out of [0, 120] range
            sex="F",
            insurance_type="Medicare",
            admission_type="Emergency",
            discharge_disposition="SNF",
            length_of_stay=6,
            comorbidity_count=4,
            charlson_index=5.0,
            prior_admissions_12mo=2,
            prior_ed_visits_12mo=3,
            num_medications=12,
            bmi=29.4,
            systolic_bp=138.0,
            glucose_level=156.0,
            creatinine=1.3,
        )


def test_scoring_request_rejects_invalid_admission_type() -> None:
    with pytest.raises(ValidationError):
        ScoringRequest(
            encounter_id="ENC-100002",
            age=50,
            sex="F",
            insurance_type="Medicare",
            admission_type="Scheduled",  # not in AdmissionType literal
            discharge_disposition="Home",
            length_of_stay=2,
            comorbidity_count=1,
            charlson_index=1.0,
            prior_admissions_12mo=0,
            prior_ed_visits_12mo=0,
            num_medications=3,
            bmi=24.0,
            systolic_bp=120.0,
            glucose_level=95.0,
            creatinine=0.9,
        )
