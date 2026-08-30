"""Proveedor Yahoo Finance con normalización y manejo de errores."""

from __future__ import annotations

import logging
import time
from datetime import date, datetime, timezone
from typing import Optional

import pandas as pd

from market_mcp.domain.models import Candle, PriceSeries
from market_mcp.providers.base import HistoricalPriceProvider

logger = logging.getLogger(__name__)

try:
    import yfinance as yf
    YF_AVAILABLE = True
except ImportError:
    yf = None  # type: ignore[assignment]
    YF_AVAILABLE = False


def _normalize_yf_symbol(symbol: str) -> str:
    s = symbol.upper().strip()
    if s.startswith("^"):
        return s
    if "." in s:
        return s
    return s


def _safe_float(value: object) -> Optional[float]:
    if value is None:
        return None
    try:
        f = float(value)
        if pd.isna(f):
            return None
        return f
    except (ValueError, TypeError):
        return None


def _yf_row_to_candle(row: pd.Series, ts: datetime) -> Candle:
    adjusted_close = _safe_float(row.get("Adj Close"))
    return Candle(
        timestamp=ts,
        open=_safe_float(row.get("Open")) or 0.0,
        high=_safe_float(row.get("High")) or 0.0,
        low=_safe_float(row.get("Low")) or 0.0,
        close=_safe_float(row.get("Close")) or 0.0,
        adjusted_close=adjusted_close,
        distribution_adjusted_close=adjusted_close,
        volume=_safe_float(row.get("Volume")),
    )


class YahooProvider(HistoricalPriceProvider):
    def __init__(self, timeout: float = 20.0, retry_attempts: int = 1, retry_delay_seconds: float = 1.0) -> None:
        self.timeout = timeout
        self.retry_attempts = max(0, retry_attempts)
        self.retry_delay_seconds = max(0.0, retry_delay_seconds)

    def get_history(
        self,
        symbol: str,
        start: date,
        end: date,
        interval: str = "1d",
        adjusted: bool = True,
    ) -> PriceSeries:
        if not YF_AVAILABLE:
            return PriceSeries(symbol=symbol, interval=interval, data_quality="empty")

        normalized = _normalize_yf_symbol(symbol)
        try:
            ticker = yf.Ticker(normalized)
        except Exception as exc:
            logger.warning("Yahoo download failed for %s: %s", normalized, exc)
            return PriceSeries(symbol=symbol, interval=interval, data_quality="empty")

        for attempt in range(self.retry_attempts + 1):
            try:
                df = ticker.history(start=start.isoformat(), end=end.isoformat(), interval=interval, auto_adjust=adjusted)
            except Exception as exc:
                logger.warning("Yahoo download failed for %s: %s", normalized, exc)
                return PriceSeries(symbol=symbol, interval=interval, data_quality="empty")

            if df is None or df.empty:
                return PriceSeries(symbol=symbol, interval=interval, data_quality="empty")

            # Yahoo can publish a session with volume before its OHLC fields
            # are available. Ignore those incomplete rows instead of marking
            # an otherwise usable historical series as invalid.
            required_ohlc = ["Open", "High", "Low", "Close"]
            if all(column in df.columns for column in required_ohlc):
                df = df.dropna(subset=required_ohlc)
            if df.empty:
                logger.warning("Yahoo returned no complete OHLC rows for %s", normalized)
                if attempt < self.retry_attempts:
                    time.sleep(self.retry_delay_seconds)
                    continue
                return PriceSeries(
                    symbol=symbol,
                    interval=interval,
                    provider="yahoo",
                    data_quality="missing",
                )

            candles: list[Candle] = []
            for ts, row in df.iterrows():
                if ts is None:
                    continue
                if hasattr(ts, "to_pydatetime"):
                    dt = ts.to_pydatetime()
                elif isinstance(ts, datetime):
                    dt = ts
                else:
                    dt = datetime.now(timezone.utc)
                candles.append(_yf_row_to_candle(row, dt))

            invalid = any(
                any(
                    value is not None and (value <= 0 or not pd.notna(value))
                    for value in (c.open, c.high, c.low, c.close, c.adjusted_close)
                )
                for c in candles
            )
            if not invalid:
                break
            if attempt < self.retry_attempts:
                logger.warning(
                    "Yahoo returned invalid OHLC for %s; retrying (%d/%d)",
                    normalized,
                    attempt + 1,
                    self.retry_attempts,
                )
                time.sleep(self.retry_delay_seconds)
            else:
                logger.warning("Yahoo returned invalid OHLC for %s after retries", normalized)
                return PriceSeries(symbol=symbol, interval=interval, provider="yahoo", data_quality="missing")

        currency: Optional[str] = None
        try:
            info = ticker.info
            currency = info.get("currency")
        except Exception:
            pass

        quality = "complete" if len(candles) > 0 else "empty"
        return PriceSeries(
            symbol=symbol,
            currency=currency,
            interval=interval,
            candles=candles,
            provider="yahoo",
            price_adjustment="auto_adjust" if adjusted else "raw",
            data_quality=quality,
        )

    def get_currency(self, symbol: str) -> Optional[str]:
        if not YF_AVAILABLE:
            return None
        normalized = _normalize_yf_symbol(symbol)
        try:
            ticker = yf.Ticker(normalized)
            return ticker.info.get("currency")
        except Exception:
            return None
