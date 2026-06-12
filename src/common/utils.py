"""Common helper utilities shared across pipeline stages."""

from __future__ import annotations

import functools
import random
import time
from pathlib import Path
from typing import Any, Callable, TypeVar

import numpy as np
import pandas as pd

from src.common.logging_utils import get_logger

logger = get_logger(__name__)

T = TypeVar("T")


def set_seed(seed: int = 42) -> None:
    """Set random seeds for ``random`` and ``numpy`` for reproducibility."""
    random.seed(seed)
    np.random.seed(seed)


def timer(func: Callable[..., T]) -> Callable[..., T]:
    """Decorator that logs the wall-clock duration of a function call."""

    @functools.wraps(func)
    def wrapper(*args: Any, **kwargs: Any) -> T:
        start = time.perf_counter()
        try:
            return func(*args, **kwargs)
        finally:
            elapsed = time.perf_counter() - start
            logger.info(
                "function_timing",
                extra={"function": func.__name__, "elapsed_seconds": round(elapsed, 4)},
            )

    return wrapper


def ensure_dir(path: str | Path) -> Path:
    """Create ``path`` (and parents) if it does not exist; return it as a ``Path``."""
    p = Path(path)
    p.mkdir(parents=True, exist_ok=True)
    return p


def read_table(path: str | Path) -> pd.DataFrame:
    """Read a CSV or Parquet file into a DataFrame based on its extension."""
    p = Path(path)
    if p.suffix == ".parquet":
        return pd.read_parquet(p)
    if p.suffix == ".csv":
        return pd.read_csv(p)
    raise ValueError(f"Unsupported file extension for read_table: {p.suffix}")


def write_table(df: pd.DataFrame, path: str | Path) -> Path:
    """Write a DataFrame to CSV or Parquet based on the destination extension."""
    p = Path(path)
    ensure_dir(p.parent)
    if p.suffix == ".parquet":
        df.to_parquet(p, index=False)
    elif p.suffix == ".csv":
        df.to_csv(p, index=False)
    else:
        raise ValueError(f"Unsupported file extension for write_table: {p.suffix}")
    logger.info("wrote_table", extra={"path": str(p), "rows": len(df), "columns": len(df.columns)})
    return p


def adls_path(storage_account_uri: str, container: str, *parts: str) -> str:
    """Build an ``abfss://`` path for an ADLS Gen2 location.

    Example:
        >>> adls_path("sthcaidev001", "curated", "features", "v1")
        'abfss://curated@sthcaidev001.dfs.core.windows.net/features/v1'
    """
    account = storage_account_uri.replace("https://", "").replace(
        ".dfs.core.windows.net", ""
    )
    suffix = "/".join(parts)
    base = f"abfss://{container}@{account}.dfs.core.windows.net"
    return f"{base}/{suffix}" if suffix else base
