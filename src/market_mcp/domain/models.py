"""Modelos de dominio normalizados para OHLCV, snapshots y señales."""

from __future__ import annotations

import math
from datetime import datetime, timezone
from typing import Any, Dict, List, Literal, Optional

from pydantic import BaseModel, Field


class Candle(BaseModel):
    timestamp: datetime
    open: float
    high: float
    low: float
    close: float
    adjusted_close: Optional[float] = None
    split_adjusted_close: Optional[float] = None
    distribution_adjusted_close: Optional[float] = None
    volume: Optional[float] = None

    def to_dict(self) -> Dict[str, Any]:
        return {
            "timestamp": self.timestamp.isoformat(),
            "open": self.open,
            "high": self.high,
            "low": self.low,
            "close": self.close,
            "adjusted_close": self.adjusted_close,
            "split_adjusted_close": self.split_adjusted_close,
            "distribution_adjusted_close": self.distribution_adjusted_close,
            "volume": self.volume,
        }


class PriceSeries(BaseModel):
    symbol: str
    currency: Optional[str] = None
    interval: str = "1d"
    candles: List[Candle] = Field(default_factory=list)
    provider: str = "yahoo"
    series_kind: Literal["price", "fred_observation"] = "price"
    fetched_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))
    price_adjustment: Literal["auto_adjust", "raw"] = "auto_adjust"
    data_quality: Literal["complete", "partial", "empty", "missing"] = "empty"


def is_valid_price_series(series: PriceSeries) -> bool:
    """Return whether a series can safely be used for market-price analysis."""
    if not series.candles or series.data_quality in {"empty", "missing"}:
        return False

    for candle in series.candles:
        values = (candle.open, candle.high, candle.low, candle.close)
        if any(not math.isfinite(value) or value <= 0 for value in values):
            return series.series_kind == "fred_observation" and all(math.isfinite(value) for value in values)
        if series.series_kind != "fred_observation":
            adjusted_values = (
                candle.adjusted_close,
                candle.split_adjusted_close,
                candle.distribution_adjusted_close,
            )
            if any(value is not None and (not math.isfinite(value) or value <= 0) for value in adjusted_values):
                return False
    return True


class IndicatorSnapshot(BaseModel):
    as_of: datetime
    price: float
    rsi14: Optional[float] = None
    macd: Optional[float] = None
    macd_signal: Optional[float] = None
    macd_histogram: Optional[float] = None
    sma20: Optional[float] = None
    sma50: Optional[float] = None
    sma100: Optional[float] = None
    sma200: Optional[float] = None


class SymbolResolution(BaseModel):
    query_symbol: str
    original_symbol: str
    resolved_symbol: Optional[str] = None
    used_equivalent: bool = False
    resolution_method: Optional[str] = None
    candidates_tried: List[str] = Field(default_factory=list)
    failed: bool = True
    failure_reason: Optional[str] = None
    note: Optional[str] = None


class ETFPriceSnapshotReport(BaseModel):
    symbol: str
    currency: Optional[str] = None
    provider: Optional[str] = None
    series_kind: Literal["price", "fred_observation"] = "price"
    original_symbol: str
    used_equivalent: bool = False
    resolution_method: Optional[str] = None
    candidates_tried: List[str] = Field(default_factory=list)
    note: Optional[str] = None
    current: Optional[IndicatorSnapshot] = None
    last_week: Optional[IndicatorSnapshot] = None
    last_month: Optional[IndicatorSnapshot] = None
    error: Optional[str] = None


class MaritimeObservation(BaseModel):
    date: str
    total_vessels: int
    tankers: int
    estimated_capacity: int
    estimated_tanker_capacity: int


class MaritimeChokepointReport(BaseModel):
    name: str
    port_id: str
    source: str = "IMF PortWatch / UN Global Platform"
    latest_date: Optional[str] = None
    freshness_days: Optional[int] = None
    status: Literal["DATA_AVAILABLE", "STALE", "NO_DATA"]
    latest: Optional[MaritimeObservation] = None
    averages: Dict[str, Dict[str, Optional[float]]] = Field(default_factory=dict)
    latest_vs_30d_average_pct: Optional[float] = None
    history: List[MaritimeObservation] = Field(default_factory=list)
    warnings: List[str] = Field(default_factory=list)
