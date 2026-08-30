"""Servicio de snapshot de precios para ETFs con indicadores en tres fechas."""

from __future__ import annotations

import logging
from datetime import datetime, timedelta, timezone
from typing import Optional

import pandas as pd

from market_mcp.domain.indicators import macd, rsi, round_value, sma
from market_mcp.domain.models import ETFPriceSnapshotReport, IndicatorSnapshot, PriceSeries, is_valid_price_series
from market_mcp.providers.base import HistoricalPriceProvider
from market_mcp.providers.symbol_resolution import SymbolResolver
from market_mcp.storage.cache import PriceCache, SnapshotCache

logger = logging.getLogger(__name__)


def _date_to_dt(d) -> datetime:
    if isinstance(d, datetime):
        return d
    return datetime(d.year, d.month, d.day, tzinfo=timezone.utc)


def _find_snapshot_for_date(series: PriceSeries, target_date: datetime, lookback_days: int = 7) -> Optional[PriceSeries]:
    target_ts = target_date.replace(hour=0, minute=0, second=0, microsecond=0)
    candles_before = []
    for c in series.candles:
        if c.timestamp.tzinfo is None:
            c_ts = c.timestamp.replace(tzinfo=timezone.utc)
        else:
            c_ts = c.timestamp.astimezone(timezone.utc)
        if c_ts <= target_ts:
            candles_before.append(c)
    if not candles_before:
        return None
    last = candles_before[-1]
    return PriceSeries(
        symbol=series.symbol,
        currency=series.currency,
        interval=series.interval,
        candles=[last],
        provider=series.provider,
        series_kind=series.series_kind,
        fetched_at=series.fetched_at,
        price_adjustment=series.price_adjustment,
        data_quality=series.data_quality,
    )


def _build_snapshot(series: PriceSeries, as_of: datetime) -> Optional[IndicatorSnapshot]:
    if not series.candles:
        return None
    last = series.candles[-1]
    if last.adjusted_close is not None and last.adjusted_close > 0:
        close_val = last.adjusted_close
    else:
        close_val = last.close

    timestamps = [c.timestamp.replace(tzinfo=timezone.utc) for c in series.candles]
    closes = pd.Series(
        [c.adjusted_close if c.adjusted_close is not None else c.close for c in series.candles],
        index=timestamps,
    )

    rsi_series = rsi(closes, 14)
    macd_df = macd(closes, 12, 26, 9)
    sma20_series = sma(closes, 20)
    sma50_series = sma(closes, 50)
    sma100_series = sma(closes, 100)
    sma200_series = sma(closes, 200)

    last_rsi = float(rsi_series.iloc[-1]) if not rsi_series.empty and not pd.isna(rsi_series.iloc[-1]) else None
    last_macd = float(macd_df["macd"].iloc[-1]) if not macd_df.empty and not pd.isna(macd_df["macd"].iloc[-1]) else None
    last_signal = float(macd_df["signal"].iloc[-1]) if not macd_df.empty and not pd.isna(macd_df["signal"].iloc[-1]) else None
    last_hist = float(macd_df["histogram"].iloc[-1]) if not macd_df.empty and not pd.isna(macd_df["histogram"].iloc[-1]) else None
    last_sma20 = float(sma20_series.iloc[-1]) if not sma20_series.empty and not pd.isna(sma20_series.iloc[-1]) else None
    last_sma50 = float(sma50_series.iloc[-1]) if not sma50_series.empty and not pd.isna(sma50_series.iloc[-1]) else None
    last_sma100 = float(sma100_series.iloc[-1]) if not sma100_series.empty and not pd.isna(sma100_series.iloc[-1]) else None
    last_sma200 = float(sma200_series.iloc[-1]) if not sma200_series.empty and not pd.isna(sma200_series.iloc[-1]) else None

    return IndicatorSnapshot(
        as_of=as_of,
        price=close_val,
        rsi14=round_value(last_rsi, 2),
        macd=round_value(last_macd, 4),
        macd_signal=round_value(last_signal, 4),
        macd_histogram=round_value(last_hist, 4),
        sma20=round_value(last_sma20, 4),
        sma50=round_value(last_sma50, 4),
        sma100=round_value(last_sma100, 4),
        sma200=round_value(last_sma200, 4),
    )


class PriceSnapshotService:
    def __init__(
        self,
        provider: HistoricalPriceProvider,
        resolver: SymbolResolver,
        price_cache: Optional[PriceCache] = None,
        snapshot_cache: Optional[SnapshotCache] = None,
    ) -> None:
        self.provider = provider
        self.resolver = resolver
        self.price_cache = price_cache
        self.snapshot_cache = snapshot_cache

    def _fetch_series(self, symbol: str, period: str, adjusted: bool = True) -> PriceSeries:
        if self.price_cache is not None:
            cached = self.price_cache.get(symbol, "1d", period, adjusted)
            if cached is not None and is_valid_price_series(cached):
                return cached

        from datetime import date, timedelta
        now = date.today()
        # Yahoo's end date is exclusive; include today's completed session by
        # using tomorrow as the upper bound.
        end = now + timedelta(days=1)
        period_map = {
            "1mo": 30,
            "3mo": 91,
            "6mo": 182,
            "1y": 365,
            "2y": 730,
            "3y": 1095,
            "5y": 1825,
        }
        days = period_map.get(period, 365)
        start = now - timedelta(days=days)

        series = self.provider.get_history(symbol, start, end, "1d", adjusted)

        if self.price_cache is not None and is_valid_price_series(series):
            self.price_cache.set(symbol, "1d", period, adjusted, series)

        return series

    def _check_symbol(self, symbol: str) -> bool:
        series = self._fetch_series(symbol, "3mo", True)
        return is_valid_price_series(series)

    def get_etf_price_snapshot(
        self,
        symbol: str,
        period: str = "2y",
        include_note: bool = True,
    ) -> ETFPriceSnapshotReport:
        resolution = self.resolver.try_resolve(symbol, self._check_symbol)

        if resolution.failed:
            return ETFPriceSnapshotReport(
                symbol=resolution.original_symbol,
                original_symbol=resolution.original_symbol,
                used_equivalent=False,
                resolution_method=resolution.resolution_method,
                candidates_tried=resolution.candidates_tried,
                error="missing_data" if resolution.failure_reason == "all_candidates_failed" else resolution.failure_reason or "all_candidates_failed",
            )

        resolved = resolution.resolved_symbol or resolution.original_symbol
        series = self._fetch_series(resolved, period, True)

        if not is_valid_price_series(series):
            return ETFPriceSnapshotReport(
                symbol=resolved,
                currency=series.currency,
                provider=series.provider,
                series_kind=series.series_kind,
                original_symbol=resolution.original_symbol,
                used_equivalent=resolution.used_equivalent,
                resolution_method=resolution.resolution_method,
                candidates_tried=resolution.candidates_tried,
                note=resolution.note,
                error="missing_data" if series.data_quality == "missing" else "no_data_available",
            )

        now = datetime.now(timezone.utc)
        last_week = now - timedelta(days=7)
        last_month = now - timedelta(days=30)

        current_snap = _build_snapshot(series, now)
        week_snap = _build_snapshot(series, last_week)
        month_snap = _build_snapshot(series, last_month)

        note_out = resolution.note if include_note else None

        return ETFPriceSnapshotReport(
            symbol=resolved,
            currency=series.currency,
            provider=series.provider,
            series_kind=series.series_kind,
            original_symbol=resolution.original_symbol,
            used_equivalent=resolution.used_equivalent,
            resolution_method=resolution.resolution_method,
            candidates_tried=resolution.candidates_tried,
            note=note_out,
            current=current_snap,
            last_week=week_snap,
            last_month=month_snap,
        )
