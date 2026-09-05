"""Tool MCP para importar caché OHLCV desde un origen externo."""

from __future__ import annotations

import json
import hashlib
import os
import tarfile
from datetime import datetime, timezone
from pathlib import Path
from urllib.parse import unquote

import pandas as pd

from market_data.domain.models import Candle, PriceSeries
from market_data.storage.cache import PriceCache


def _parquet_to_price_series(df: pd.DataFrame, symbol: str) -> PriceSeries:
    if df.empty:
        return PriceSeries(symbol=symbol, interval="1d", candles=[], provider="parquet_import")

    candles: list[Candle] = []
    for ts, row in df.iterrows():
        if ts is None:
            continue
        if hasattr(ts, "to_pydatetime"):
            dt = ts.to_pydatetime()
        elif isinstance(ts, datetime):
            dt = ts
        else:
            dt = _parse_timestamp(ts)
        if dt.tzinfo is None:
            dt = dt.replace(tzinfo=timezone.utc)

        candles.append(
            Candle(
                timestamp=dt,
                open=_safe_float(row.get("Open")) or 0.0,
                high=_safe_float(row.get("High")) or 0.0,
                low=_safe_float(row.get("Low")) or 0.0,
                close=_safe_float(row.get("Close")) or 0.0,
                adjusted_close=_safe_float(row.get("Adj Close") or row.get("adjusted_close")),
                volume=_safe_float(row.get("Volume") or row.get("volume")),
            )
        )

    return PriceSeries(
        symbol=unquote(symbol).upper(),
        interval="1d",
        candles=candles,
        provider="parquet_import",
        price_adjustment="auto_adjust",
        data_quality="complete" if candles else "empty",
    )


def _safe_float(value) -> float | None:
    try:
        import numpy as np

        if pd.isna(value) or (isinstance(value, float) and np.isnan(value)):
            return None
    except Exception:
        pass

    try:
        return float(value)
    except (ValueError, TypeError):
        return None


def _parse_timestamp(value) -> datetime:
    ts = pd.to_datetime(value, utc=True, errors="coerce")
    if pd.isna(ts):
        return datetime.now(timezone.utc)
    return ts.to_pydatetime()


def _rows_to_price_series(rows: list[dict], symbol: str, provider: str) -> PriceSeries:
    candles: list[Candle] = []
    for row in rows:
        if not isinstance(row, dict):
            continue

        timestamp = row.get("timestamp") or row.get("date") or row.get("Date")
        if timestamp is None:
            continue

        candles.append(
            Candle(
                timestamp=_parse_timestamp(timestamp),
                open=_safe_float(row.get("Open")) or 0.0,
                high=_safe_float(row.get("High")) or 0.0,
                low=_safe_float(row.get("Low")) or 0.0,
                close=_safe_float(row.get("Close")) or 0.0,
                adjusted_close=_safe_float(row.get("Adj Close") or row.get("adjusted_close")),
                volume=_safe_float(row.get("Volume") or row.get("volume")),
            )
        )

    return PriceSeries(
        symbol=unquote(symbol).upper(),
        interval="1d",
        candles=candles,
        provider=provider,
        price_adjustment="auto_adjust",
        data_quality="complete" if candles else "empty",
    )


def _json_to_price_series(payload: dict, symbol: str) -> PriceSeries:
    if not isinstance(payload, dict):
        return PriceSeries(symbol=unquote(symbol).upper(), interval="1d", candles=[], provider="json_import")

    meta = payload.get("meta") or {}
    rows = payload.get("rows")
    if rows is None:
        rows = payload.get("candles") or []

    provider = meta.get("source") or "json_import"
    series = _rows_to_price_series(rows, meta.get("symbol") or symbol, provider=provider)
    if meta.get("first_date") or meta.get("last_date"):
        series.data_quality = "complete" if series.candles else "empty"
    return series


def bootstrap_cache_from_external(
    source_dir: str,
    target_cache_dir: str | None = None,
    dry_run: bool = False,
) -> dict:
    source = Path(source_dir)
    resolved_target = target_cache_dir or os.environ.get("MARKET_DATA_ROOT")
    if not resolved_target:
        raise RuntimeError("MARKET_DATA_ROOT is required when target_cache_dir is omitted")
    target = Path(resolved_target).expanduser() / "ohlcv_cache" if target_cache_dir is None else Path(resolved_target)

    if not source.exists():
        return {"error": f"Source directory not found: {source_dir}"}

    parquet_files = []
    json_files = []
    tar_members = []

    if source.is_file() and source.suffixes[-2:] == [".tar", ".gz"]:
        with tarfile.open(source, "r:gz") as archive:
            tar_members = [
                m
                for m in archive.getmembers()
                if m.isfile() and m.name.endswith(".json") and "/._" not in m.name
            ]
            if not tar_members:
                return {"error": "No JSON cache files found in tar.gz source", "source": source_dir}
    else:
        parquet_files = list(source.glob("*.parquet"))
        json_files = [p for p in source.glob("*.json") if not p.name.startswith("._")]
        if not parquet_files and not json_files:
            return {"error": "No parquet or json files found in source directory", "source": source_dir}

    price_cache = None
    if not dry_run:
        price_cache = PriceCache(cache_dir=target, ttl_seconds=21600)

    imported = 0
    errors = 0

    def _store_series(symbol: str, series: PriceSeries) -> None:
        nonlocal imported
        if not dry_run and price_cache is not None:
            price_cache.set(symbol, "1d", "1y", True, series)
        imported += 1

    for pf in parquet_files:
        symbol = unquote(pf.stem).upper()
        try:
            df = pd.read_parquet(pf)
            if df is None or df.empty:
                continue
            series = _parquet_to_price_series(df, symbol)
            _store_series(symbol, series)
        except Exception:
            errors += 1

    for jf in json_files:
        symbol = unquote(jf.stem).upper()
        try:
            payload = json.loads(jf.read_text(encoding="utf-8"))
            series = _json_to_price_series(payload, symbol)
            if not series.candles:
                continue
            _store_series(symbol, series)
        except Exception:
            errors += 1

    if tar_members:
        with tarfile.open(source, "r:gz") as archive:
            for member in tar_members:
                symbol = unquote(Path(member.name).stem).upper()
                try:
                    payload = json.load(archive.extractfile(member))
                    series = _json_to_price_series(payload, symbol)
                    if not series.candles:
                        continue
                    _store_series(symbol, series)
                except Exception:
                    errors += 1

    return {
        "source": source_dir,
        "target": str(target),
        "dry_run": dry_run,
        "imported": imported,
        "errors": errors,
        "total_files": len(parquet_files) + len(json_files) + len(tar_members),
    }
