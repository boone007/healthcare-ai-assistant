"""Feature store interface.

This module provides a thin abstraction over the curated feature table so
that training and scoring code depend on a stable interface
(``get_offline_features`` / ``get_online_features``) rather than directly on
file paths or storage clients. The default implementation is backed by
Parquet files on local disk or ADLS Gen2 (via ``abfss://`` paths supported by
``pandas``/``pyarrow`` with the ``adlfs`` filesystem).

In a future iteration this interface can be implemented against the **Azure
ML Managed Feature Store** without changing any calling code.
"""

from __future__ import annotations

from abc import ABC, abstractmethod
from pathlib import Path

import pandas as pd

from src.common.logging_utils import get_logger
from src.common.schemas import MODEL_FEATURE_COLUMNS

logger = get_logger(__name__)


class FeatureStore(ABC):
    """Abstract interface for retrieving engineered features."""

    @abstractmethod
    def get_offline_features(self) -> pd.DataFrame:
        """Return the full historical feature table (including labels) for training."""

    @abstractmethod
    def get_online_features(self, encounter_ids: list[str]) -> pd.DataFrame:
        """Return feature rows for the given ``encounter_ids`` for low-latency scoring."""


class ParquetFeatureStore(FeatureStore):
    """A feature store backed by a single Parquet feature table.

    Args:
        table_path: Local path or ``abfss://`` URI to the curated feature
            table (e.g. produced by ``src/data_pipeline/transform.py``).
    """

    def __init__(self, table_path: str | Path):
        self.table_path = str(table_path)
        self._cache: pd.DataFrame | None = None

    def _load(self) -> pd.DataFrame:
        if self._cache is None:
            logger.info("feature_store_load", extra={"table_path": self.table_path})
            self._cache = pd.read_parquet(self.table_path)
        return self._cache

    def get_offline_features(self) -> pd.DataFrame:
        """Return the full feature table for training (includes the label column)."""
        return self._load().copy()

    def get_online_features(self, encounter_ids: list[str]) -> pd.DataFrame:
        """Return feature rows (model columns only) for the requested encounter IDs.

        Raises:
            KeyError: if any requested ``encounter_id`` is not present in the
                feature table.
        """
        df = self._load()
        subset = df[df["encounter_id"].isin(encounter_ids)]

        missing = set(encounter_ids) - set(subset["encounter_id"])
        if missing:
            raise KeyError(f"encounter_id(s) not found in feature store: {sorted(missing)}")

        return subset[["encounter_id", *MODEL_FEATURE_COLUMNS]].copy()


def get_feature_store(table_path: str | Path) -> FeatureStore:
    """Factory returning the configured :class:`FeatureStore` implementation."""
    return ParquetFeatureStore(table_path)
