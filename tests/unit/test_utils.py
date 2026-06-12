"""Unit tests for src/common/utils.py."""

from __future__ import annotations

from pathlib import Path

import pandas as pd
import pytest

from src.common.utils import adls_path, ensure_dir, read_table, write_table


def test_ensure_dir_creates_nested_directories(tmp_path: Path) -> None:
    target = tmp_path / "a" / "b" / "c"
    result = ensure_dir(target)

    assert result == target
    assert target.is_dir()


def test_write_and_read_table_roundtrip_csv(tmp_path: Path) -> None:
    df = pd.DataFrame({"a": [1, 2], "b": ["x", "y"]})
    path = tmp_path / "out" / "data.csv"

    write_table(df, path)
    loaded = read_table(path)

    pd.testing.assert_frame_equal(loaded, df)


def test_write_and_read_table_roundtrip_parquet(tmp_path: Path) -> None:
    df = pd.DataFrame({"a": [1, 2], "b": ["x", "y"]})
    path = tmp_path / "out" / "data.parquet"

    write_table(df, path)
    loaded = read_table(path)

    pd.testing.assert_frame_equal(loaded, df)


def test_read_table_rejects_unsupported_extension(tmp_path: Path) -> None:
    path = tmp_path / "data.txt"
    path.write_text("not a table", encoding="utf-8")

    with pytest.raises(ValueError):
        read_table(path)


def test_adls_path_builds_abfss_uri() -> None:
    uri = adls_path("https://sthcaidev001.dfs.core.windows.net", "curated", "features", "v1")
    assert uri == "abfss://curated@sthcaidev001.dfs.core.windows.net/features/v1"


def test_adls_path_without_parts() -> None:
    uri = adls_path("https://sthcaidev001.dfs.core.windows.net", "raw")
    assert uri == "abfss://raw@sthcaidev001.dfs.core.windows.net"
