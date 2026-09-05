"""Tests for invalid Yahoo OHLC retry handling."""

from __future__ import annotations

from datetime import date
from unittest.mock import patch

import pandas as pd

from market_data.providers.yahoo import YahooProvider


def _frame(close: float) -> pd.DataFrame:
    return pd.DataFrame(
        {"Open": [close], "High": [close], "Low": [close], "Close": [close], "Adj Close": [close], "Volume": [1000]},
        index=pd.DatetimeIndex(["2026-08-14"]),
    )


class _Ticker:
    def __init__(self, frames: list[pd.DataFrame]) -> None:
        self.frames = iter(frames)

    def history(self, **kwargs: object) -> pd.DataFrame:
        return next(self.frames)


def test_yahoo_retries_invalid_ohlc_then_returns_valid_series() -> None:
    ticker = _Ticker([_frame(0.0), _frame(61.84)])
    with patch("market_data.providers.yahoo.yf.Ticker", return_value=ticker), patch("market_data.providers.yahoo.time.sleep") as pause:
        series = YahooProvider(retry_attempts=1, retry_delay_seconds=0.25).get_history("XDWH.L", date(2026, 8, 1), date(2026, 8, 16))

    assert series.data_quality == "complete"
    assert series.candles[-1].close == 61.84
    pause.assert_called_once_with(0.25)


def test_yahoo_reports_missing_after_persistent_invalid_ohlc() -> None:
    ticker = _Ticker([_frame(0.0), _frame(0.0)])
    with patch("market_data.providers.yahoo.yf.Ticker", return_value=ticker), patch("market_data.providers.yahoo.time.sleep"):
        series = YahooProvider(retry_attempts=1, retry_delay_seconds=0).get_history("XDWH.L", date(2026, 8, 1), date(2026, 8, 16))

    assert series.data_quality == "missing"
    assert series.candles == []


def test_yahoo_retries_zero_adjusted_close() -> None:
    invalid = _frame(61.84)
    invalid["Adj Close"] = 0.0
    ticker = _Ticker([invalid, _frame(61.84)])
    with patch("market_data.providers.yahoo.yf.Ticker", return_value=ticker), patch("market_data.providers.yahoo.time.sleep") as pause:
        series = YahooProvider(retry_attempts=1).get_history("XDWH.L", date(2026, 8, 1), date(2026, 8, 16))

    assert series.data_quality == "complete"
    pause.assert_called_once_with(1.0)


def test_yahoo_ignores_incomplete_ohlc_rows() -> None:
    frame = _frame(61.84)
    incomplete = pd.DataFrame(
        {
            "Open": [float("nan")],
            "High": [float("nan")],
            "Low": [float("nan")],
            "Close": [float("nan")],
            "Adj Close": [float("nan")],
            "Volume": [1000],
        },
        index=pd.DatetimeIndex(["2026-08-15"]),
    )
    frame = pd.concat([frame, incomplete])
    ticker = _Ticker([frame])
    with (
        patch("market_data.providers.yahoo.yf.Ticker", return_value=ticker),
        patch("market_data.providers.yahoo.time.sleep") as pause,
    ):
        series = YahooProvider(retry_attempts=1).get_history(
            "CBU7.L", date(2026, 8, 1), date(2026, 8, 16)
        )

    assert series.data_quality == "complete"
    assert len(series.candles) == 1
    assert series.candles[0].close == 61.84
    pause.assert_not_called()
