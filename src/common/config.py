"""Centralized configuration loading.

Configuration is layered, in increasing priority order:

1. Defaults defined in this module
2. A YAML config file (e.g. ``configs/train_config.yaml``)
3. Environment variables (e.g. ``HCAI_ENV``, ``HCAI_KEY_VAULT_URI``)
4. Secrets resolved from Azure Key Vault at runtime (optional)

This keeps environment-specific values (resource names, thresholds) out of
code while allowing local development without any Azure dependencies.
"""

from __future__ import annotations

import os
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

import yaml

DEFAULT_CONFIG: dict[str, Any] = {
    "environment": "dev",
    "data": {
        "raw_container": "raw",
        "curated_container": "curated",
        "models_container": "models",
        "monitoring_container": "monitoring",
    },
    "model": {
        "algorithm": "lightgbm",  # or "xgboost"
        "name": "readmission-risk-model",
        "random_seed": 42,
        "hyperparameters": {
            "num_leaves": 31,
            "learning_rate": 0.05,
            "n_estimators": 300,
            "min_child_samples": 20,
            "feature_fraction": 0.9,
        },
    },
    "evaluation": {
        "decision_threshold": 0.5,
        "promotion_gate": {
            "min_roc_auc": 0.70,
            "min_pr_auc": 0.35,
            "max_brier_score": 0.20,
            "max_equalized_odds_difference": 0.10,
        },
    },
    "monitoring": {
        "psi_threshold": 0.2,
        "ks_pvalue_threshold": 0.01,
    },
}


@dataclass
class Settings:
    """Resolved application settings.

    Attributes:
        environment: Deployment environment name (``dev`` or ``prod``).
        key_vault_uri: URI of the Azure Key Vault for secret resolution,
            e.g. ``https://kv-hcai-dev.vault.azure.net/``. ``None`` for
            local-only runs.
        storage_account_uri: ADLS Gen2 endpoint for the environment's
            storage account, e.g.
            ``https://sthcaidev001.dfs.core.windows.net``.
        aml_workspace_name: Name of the Azure ML workspace, e.g.
            ``mlw-hcai-dev``.
        config: The merged configuration dictionary (defaults + YAML file).
    """

    environment: str
    key_vault_uri: str | None
    storage_account_uri: str | None
    aml_workspace_name: str | None
    config: dict[str, Any] = field(default_factory=dict)

    def get(self, *keys: str, default: Any = None) -> Any:
        """Retrieve a nested configuration value.

        Example:
            >>> settings.get("model", "hyperparameters", "learning_rate")
        """
        node: Any = self.config
        for key in keys:
            if not isinstance(node, dict) or key not in node:
                return default
            node = node[key]
        return node


def _deep_merge(base: dict[str, Any], override: dict[str, Any]) -> dict[str, Any]:
    """Recursively merge ``override`` into ``base``, returning a new dict."""
    merged = dict(base)
    for key, value in override.items():
        if key in merged and isinstance(merged[key], dict) and isinstance(value, dict):
            merged[key] = _deep_merge(merged[key], value)
        else:
            merged[key] = value
    return merged


def load_config(config_path: str | Path | None = None) -> dict[str, Any]:
    """Load and merge configuration from defaults and an optional YAML file."""
    config = dict(DEFAULT_CONFIG)
    if config_path is not None:
        path = Path(config_path)
        if path.exists():
            with path.open("r", encoding="utf-8") as fh:
                file_config = yaml.safe_load(fh) or {}
            config = _deep_merge(config, file_config)
    return config


def get_settings(config_path: str | Path | None = None) -> Settings:
    """Build a :class:`Settings` instance from environment variables and YAML.

    Environment variables consulted:

    - ``HCAI_ENV`` (default: ``dev``)
    - ``HCAI_KEY_VAULT_URI``
    - ``HCAI_STORAGE_ACCOUNT_URI``
    - ``HCAI_AML_WORKSPACE_NAME``
    - ``HCAI_CONFIG_PATH`` (used if ``config_path`` is not provided)
    """
    environment = os.environ.get("HCAI_ENV", "dev")
    resolved_config_path = config_path or os.environ.get("HCAI_CONFIG_PATH")
    config = load_config(resolved_config_path)
    config["environment"] = environment

    return Settings(
        environment=environment,
        key_vault_uri=os.environ.get("HCAI_KEY_VAULT_URI"),
        storage_account_uri=os.environ.get("HCAI_STORAGE_ACCOUNT_URI"),
        aml_workspace_name=os.environ.get("HCAI_AML_WORKSPACE_NAME"),
        config=config,
    )


def get_secret(name: str, settings: Settings | None = None, default: str | None = None) -> str | None:
    """Resolve a secret from Azure Key Vault, falling back to an env var.

    Looks up environment variable ``HCAI_SECRET_<NAME_UPPER>`` first (useful
    for local development and CI), then falls back to Key Vault if
    ``settings.key_vault_uri`` is configured. Returns ``default`` if neither
    source has the secret.
    """
    env_key = f"HCAI_SECRET_{name.upper().replace('-', '_')}"
    if env_key in os.environ:
        return os.environ[env_key]

    settings = settings or get_settings()
    if settings.key_vault_uri:
        try:
            from azure.identity import DefaultAzureCredential
            from azure.keyvault.secrets import SecretClient

            credential = DefaultAzureCredential()
            client = SecretClient(vault_url=settings.key_vault_uri, credential=credential)
            return client.get_secret(name).value
        except Exception:  # pragma: no cover - best-effort fallback
            return default

    return default
