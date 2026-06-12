"""Unit tests for src/common/config.py."""

from __future__ import annotations

from pathlib import Path

from src.common.config import DEFAULT_CONFIG, Settings, _deep_merge, get_secret, get_settings, load_config


def test_deep_merge_overrides_nested_keys() -> None:
    base = {"a": {"b": 1, "c": 2}, "d": 4}
    override = {"a": {"b": 99}, "e": 5}

    merged = _deep_merge(base, override)

    assert merged == {"a": {"b": 99, "c": 2}, "d": 4, "e": 5}
    # Inputs are not mutated.
    assert base["a"]["b"] == 1


def test_load_config_without_path_returns_defaults() -> None:
    config = load_config(None)
    assert config == DEFAULT_CONFIG


def test_load_config_merges_yaml_overrides(tmp_path: Path) -> None:
    config_file = tmp_path / "train_config.yaml"
    config_file.write_text(
        "model:\n  algorithm: xgboost\n  hyperparameters:\n    learning_rate: 0.01\n",
        encoding="utf-8",
    )

    config = load_config(config_file)

    assert config["model"]["algorithm"] == "xgboost"
    assert config["model"]["hyperparameters"]["learning_rate"] == 0.01
    # Other default hyperparameters remain.
    assert config["model"]["hyperparameters"]["num_leaves"] == DEFAULT_CONFIG["model"]["hyperparameters"]["num_leaves"]
    # Unrelated defaults remain.
    assert config["evaluation"]["promotion_gate"]["min_roc_auc"] == DEFAULT_CONFIG["evaluation"]["promotion_gate"]["min_roc_auc"]


def test_load_config_ignores_missing_path(tmp_path: Path) -> None:
    missing = tmp_path / "does_not_exist.yaml"
    config = load_config(missing)
    assert config == DEFAULT_CONFIG


def test_settings_get_nested_value_and_default() -> None:
    settings = Settings(environment="dev", key_vault_uri=None, storage_account_uri=None, aml_workspace_name=None, config=DEFAULT_CONFIG)

    assert settings.get("model", "hyperparameters", "learning_rate") == 0.05
    assert settings.get("model", "does_not_exist", default="fallback") == "fallback"
    assert settings.get("does_not_exist", default="fallback") == "fallback"


def test_get_settings_reads_environment_variables(monkeypatch) -> None:
    monkeypatch.setenv("HCAI_ENV", "prod")
    monkeypatch.setenv("HCAI_KEY_VAULT_URI", "https://kv-hcai-prod.vault.azure.net/")
    monkeypatch.delenv("HCAI_CONFIG_PATH", raising=False)

    settings = get_settings()

    assert settings.environment == "prod"
    assert settings.key_vault_uri == "https://kv-hcai-prod.vault.azure.net/"
    assert settings.config["environment"] == "prod"


def test_get_secret_falls_back_to_environment_variable(monkeypatch) -> None:
    monkeypatch.setenv("HCAI_SECRET_AML_ENDPOINT_KEY", "super-secret-value")

    value = get_secret("aml-endpoint-key")

    assert value == "super-secret-value"


def test_get_secret_returns_default_when_unresolved(monkeypatch) -> None:
    monkeypatch.delenv("HCAI_SECRET_UNKNOWN", raising=False)
    monkeypatch.delenv("HCAI_KEY_VAULT_URI", raising=False)

    value = get_secret("unknown", default="fallback-value")

    assert value == "fallback-value"
