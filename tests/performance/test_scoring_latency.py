"""Performance tests for the AML scoring script (src/deployment/scoring/score.py).

These tests measure single-request and batch scoring latency using the same
``init()`` / ``run()`` entry points the managed online endpoint invokes, with
the locally-trained ``model_bundle`` fixture standing in for the registered
model artifact. Thresholds are intentionally generous (suitable for a CI
runner) — see ``docs/runbook-operations.md`` §4 for the production
``HighScoringLatencyP95`` alert threshold (1000ms p95, measured in
Application Insights).

Run only these tests with:
    pytest tests/performance -m performance
"""

from __future__ import annotations

import json
import time
from pathlib import Path

import joblib
import pytest

from src.deployment.scoring import score

pytestmark = pytest.mark.performance


@pytest.fixture()
def initialized_score_module(model_bundle: dict, tmp_path: Path, monkeypatch: pytest.MonkeyPatch):
    """Persist ``model_bundle`` and run score.init() against it."""
    model_dir = tmp_path / "model"
    model_dir.mkdir()
    joblib.dump(model_bundle, model_dir / "model.pkl")

    monkeypatch.setenv("AZUREML_MODEL_DIR", str(model_dir))
    monkeypatch.setenv("MODEL_VERSION", "readmission-risk-model:test")

    score.init()
    return score


SAMPLE_RECORD = {
    "encounter_id": "ENC-PERF-0001",
    "age": 74,
    "sex": "F",
    "insurance_type": "Medicare",
    "admission_type": "Emergency",
    "discharge_disposition": "SNF",
    "length_of_stay": 6,
    "comorbidity_count": 4,
    "charlson_index": 5.0,
    "prior_admissions_12mo": 2,
    "prior_ed_visits_12mo": 3,
    "num_medications": 12,
    "bmi": 29.4,
    "systolic_bp": 138.0,
    "glucose_level": 156.0,
    "creatinine": 1.3,
}


def test_single_request_latency(initialized_score_module) -> None:
    payload = json.dumps(SAMPLE_RECORD)

    start = time.perf_counter()
    response = json.loads(initialized_score_module.run(payload))
    elapsed_ms = (time.perf_counter() - start) * 1000

    assert "readmission_probability" in response
    assert elapsed_ms < 1000, f"Single-request scoring took {elapsed_ms:.1f}ms, expected < 1000ms"


def test_batch_request_latency_per_record(initialized_score_module) -> None:
    batch_size = 50
    payload = json.dumps({"data": [SAMPLE_RECORD for _ in range(batch_size)]})

    start = time.perf_counter()
    response = json.loads(initialized_score_module.run(payload))
    elapsed_ms = (time.perf_counter() - start) * 1000

    assert len(response["results"]) == batch_size

    per_record_ms = elapsed_ms / batch_size
    assert per_record_ms < 100, f"Batch scoring averaged {per_record_ms:.2f}ms/record, expected < 100ms"
