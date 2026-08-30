"""Caché en disco para OHLCV y snapshots usando diskcache."""

from __future__ import annotations

import hashlib
import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, Optional

import diskcache

from market_mcp.domain.models import Candle, IndicatorSnapshot, PriceSeries


def _serialize_price_series(series: PriceSeries) -> str:
    return series.model_dump_json()


def _deserialize_price_series(data: str) -> PriceSeries:
    return PriceSeries.model_validate_json(data)


class PriceCache:
    def __init__(self, cache_dir: Path, ttl_seconds: int = 21600) -> None:
        cache_dir.mkdir(parents=True, exist_ok=True)
        self._cache = diskcache.Cache(str(cache_dir))
        self._ttl = ttl_seconds

    def _key(self, symbol: str, interval: str, period: str, adjusted: bool) -> str:
        raw = f"{symbol.upper()}:{interval}:{period}:{adjusted}"
        return hashlib.md5(raw.encode()).hexdigest()

    def get(self, symbol: str, interval: str, period: str, adjusted: bool) -> Optional[PriceSeries]:
        key = self._key(symbol, interval, period, adjusted)
        entry, expire_time = self._cache.get(key, default=None, expire_time=True)
        if entry is None:
            return None
        if expire_time is not None and expire_time < datetime.now(timezone.utc).timestamp():
            return None
        try:
            return _deserialize_price_series(entry)
        except Exception:
            return None

    def set(self, symbol: str, interval: str, period: str, adjusted: bool, series: PriceSeries) -> None:
        key = self._key(symbol, interval, period, adjusted)
        self._cache.set(key, _serialize_price_series(series), expire=self._ttl)

    def clear(self) -> int:
        count = len(self._cache)
        self._cache.clear()
        return count


class SnapshotCache:
    def __init__(self, cache_dir: Path, ttl_seconds: int = 3600) -> None:
        cache_dir.mkdir(parents=True, exist_ok=True)
        self._cache = diskcache.Cache(str(cache_dir))
        self._ttl = ttl_seconds

    def _key(self, symbol: str, snapshot_date: str) -> str:
        raw = f"snapshot:{symbol.upper()}:{snapshot_date}"
        return hashlib.md5(raw.encode()).hexdigest()

    def get(self, symbol: str, snapshot_date: str) -> Optional[IndicatorSnapshot]:
        key = self._key(symbol, snapshot_date)
        entry, expire_time = self._cache.get(key, default=None, expire_time=True)
        if entry is None:
            return None
        if expire_time is not None and expire_time < datetime.now(timezone.utc).timestamp():
            return None
        try:
            return IndicatorSnapshot.model_validate_json(entry)
        except Exception:
            return None

    def set(self, symbol: str, snapshot_date: str, snapshot: IndicatorSnapshot) -> None:
        key = self._key(symbol, snapshot_date)
        self._cache.set(key, snapshot.model_dump_json(), expire=self._ttl)

    def clear(self) -> int:
        count = len(self._cache)
        self._cache.clear()
        return count
