"""Tests para bootstrap de caché OHLCV."""

from __future__ import annotations

import io
import json
import tarfile
from pathlib import Path

from market_mcp.storage.cache import PriceCache
from market_mcp.tools.bootstrap import bootstrap_cache_from_external


def _write_json_tarball(path: Path, name: str, payload: dict) -> None:
    data = json.dumps(payload).encode("utf-8")
    with tarfile.open(path, "w:gz") as archive:
        info = tarfile.TarInfo(name=name)
        info.size = len(data)
        archive.addfile(info, io.BytesIO(data))


def test_bootstrap_cache_from_external_imports_json_tarball(tmp_path: Path) -> None:
    source = tmp_path / "ohlcv_cache_2026-07-18.tar.gz"
    target = tmp_path / "cache"

    _write_json_tarball(
        source,
        "ohlcv_cache/MSFT.json",
        {
            "meta": {
                "symbol": "MSFT",
                "source": "yfinance",
                "first_date": "2023-05-01",
                "last_date": "2023-05-02",
            },
            "rows": [
                {
                    "date": "2023-05-01",
                    "Open": 306.97,
                    "High": 308.6,
                    "Low": 305.15,
                    "Close": 305.56,
                    "Adj Close": 298.49,
                    "Volume": 21294100,
                },
                {
                    "date": "2023-05-02",
                    "Open": 307.0,
                    "High": 310.0,
                    "Low": 304.0,
                    "Close": 309.0,
                    "Adj Close": 301.0,
                    "Volume": 22222222,
                },
            ],
        },
    )

    result = bootstrap_cache_from_external(str(source), target_cache_dir=str(target), dry_run=False)

    assert result["imported"] == 1
    assert result["errors"] == 0
    assert result["total_files"] == 1

    cache = PriceCache(cache_dir=target, ttl_seconds=21600)
    series = cache.get("MSFT", "1d", "1y", True)
    assert series is not None
    assert series.symbol == "MSFT"
    assert len(series.candles) == 2
    assert series.candles[0].close == 305.56
    assert series.candles[0].timestamp.tzinfo is not None
