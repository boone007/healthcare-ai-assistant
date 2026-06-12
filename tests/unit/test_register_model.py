"""Unit tests for src/ml_pipeline/register_model.py."""

from __future__ import annotations

from src.common.config import load_config
from src.ml_pipeline.register_model import check_promotion_gate


def _passing_metrics() -> dict:
    return {"roc_auc": 0.80, "pr_auc": 0.45, "brier_score": 0.15}


def _passing_fairness_report() -> dict:
    return {
        "groups": {
            "sex": {"equalized_odds_difference": 0.05},
            "ethnicity": {"equalized_odds_difference": 0.08},
            "age_band": {"equalized_odds_difference": 0.30},  # not enforced, see docs/responsible-ai-report.md
        }
    }


def test_check_promotion_gate_passes_when_all_thresholds_met() -> None:
    config = load_config(None)

    failures = check_promotion_gate(_passing_metrics(), _passing_fairness_report(), config)

    assert failures == []


def test_check_promotion_gate_fails_on_low_roc_auc() -> None:
    config = load_config(None)
    metrics = _passing_metrics()
    metrics["roc_auc"] = 0.60  # below default min_roc_auc of 0.70

    failures = check_promotion_gate(metrics, _passing_fairness_report(), config)

    assert any("roc_auc" in f for f in failures)


def test_check_promotion_gate_fails_on_high_brier_score() -> None:
    config = load_config(None)
    metrics = _passing_metrics()
    metrics["brier_score"] = 0.35  # above default max_brier_score of 0.20

    failures = check_promotion_gate(metrics, _passing_fairness_report(), config)

    assert any("brier_score" in f for f in failures)


def test_check_promotion_gate_fails_on_sex_equalized_odds_difference() -> None:
    config = load_config(None)
    fairness_report = _passing_fairness_report()
    fairness_report["groups"]["sex"]["equalized_odds_difference"] = 0.40  # above default 0.10

    failures = check_promotion_gate(_passing_metrics(), fairness_report, config)

    assert any("equalized_odds_difference[sex]" in f for f in failures)


def test_check_promotion_gate_does_not_enforce_age_band_disparity() -> None:
    """age_band is a documented exception (docs/responsible-ai-report.md sec 3.2/5)."""
    config = load_config(None)
    fairness_report = _passing_fairness_report()
    fairness_report["groups"]["age_band"]["equalized_odds_difference"] = 0.95

    failures = check_promotion_gate(_passing_metrics(), fairness_report, config)

    assert failures == []


def test_check_promotion_gate_handles_missing_fairness_group() -> None:
    config = load_config(None)
    fairness_report = {"groups": {"sex": {"equalized_odds_difference": 0.05}}}  # ethnicity missing

    failures = check_promotion_gate(_passing_metrics(), fairness_report, config)

    assert failures == []
