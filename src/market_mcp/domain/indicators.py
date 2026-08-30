"""Cálculo de indicadores técnicos sobre series OHLCV usando pandas y numpy."""

from __future__ import annotations

from typing import Optional

import numpy as np
import pandas as pd


def _ema(series: pd.Series, period: int) -> pd.Series:
    return series.ewm(span=period, adjust=False, min_periods=period).mean()


def rsi(close: pd.Series, period: int = 14) -> pd.Series:
    if close.empty:
        return pd.Series(dtype=float)
    delta = close.diff()
    gain = delta.clip(lower=0.0)
    loss = -delta.clip(upper=0.0)
    avg_gain = gain.ewm(alpha=1 / period, adjust=False, min_periods=period).mean()
    avg_loss = loss.ewm(alpha=1 / period, adjust=False, min_periods=period).mean()
    rs = avg_gain / avg_loss.replace(to_replace=0.0, value=np.nan)
    rsi_values = 100.0 - (100.0 / (1.0 + rs))
    return rsi_values


def macd(
    close: pd.Series,
    fast: int = 12,
    slow: int = 26,
    signal: int = 9,
) -> pd.DataFrame:
    if close.empty:
        return pd.DataFrame(columns=["macd", "signal", "histogram"])
    ema_fast = _ema(close, fast)
    ema_slow = _ema(close, slow)
    macd_line = ema_fast - ema_slow
    signal_line = _ema(macd_line, signal)
    histogram = macd_line - signal_line
    return pd.DataFrame(
        {"macd": macd_line, "signal": signal_line, "histogram": histogram}
    )


def sma(close: pd.Series, period: int) -> pd.Series:
    if close.empty:
        return pd.Series(dtype=float)
    return close.rolling(window=period, min_periods=period).mean()


def atr(high: pd.Series, low: pd.Series, close: pd.Series, period: int = 14) -> pd.Series:
    if close.empty:
        return pd.Series(dtype=float)
    prev_close = close.shift(1)
    tr = pd.concat(
        [
            (high - low).abs(),
            (high - prev_close).abs(),
            (low - prev_close).abs(),
        ],
        axis=1,
    ).max(axis=1)
    return tr.rolling(window=period, min_periods=period).mean()


def round_value(value: Optional[float], ndigits: int = 4) -> Optional[float]:
    if value is None:
        return None
    if pd.isna(value):
        return None
    return float(round(float(value), ndigits))
