"""Tests para indicadores técnicos."""

from __future__ import annotations

import pandas as pd

from market_mcp.domain.indicators import atr, macd, rsi, round_value, sma


def _make_close_series(values: list[float]) -> pd.Series:
    return pd.Series(values)


class TestRSI:
    def test_basic_rsi(self):
        closes = _make_close_series([44, 44.34, 44.09, 43.61, 44.33, 44.83, 45.10, 45.42, 45.84, 46.08, 45.89, 46.03, 45.61, 46.28, 46.28, 46.00, 46.03, 46.41, 46.22, 45.64])
        result = rsi(closes, 14)
        assert not result.empty
        last_val = float(result.iloc[-1])
        assert 0 <= last_val <= 100

    def test_empty_series(self):
        closes = _make_close_series([])
        result = rsi(closes, 14)
        assert result.empty


class TestMACD:
    def test_basic_macd(self):
        closes = _make_close_series([i + 10.0 for i in range(40)])
        result = macd(closes, 12, 26, 9)
        assert "macd" in result.columns
        assert "signal" in result.columns
        assert "histogram" in result.columns
        assert len(result) == 40

    def test_empty_series(self):
        closes = _make_close_series([])
        result = macd(closes, 12, 26, 9)
        assert result.empty


class TestSMA:
    def test_basic_sma(self):
        closes = _make_close_series([10, 11, 12, 13, 14, 15, 16, 17, 18, 19, 20])
        result = sma(closes, 5)
        assert not result.empty
        assert result.iloc[-1] == 18.0

    def test_empty_series(self):
        closes = _make_close_series([])
        result = sma(closes, 5)
        assert result.empty


class TestATR:
    def test_basic_atr(self):
        high = _make_close_series([15, 16, 17, 18, 19, 20, 21, 22, 23, 24, 25])
        low = _make_close_series([10, 11, 12, 13, 14, 15, 16, 17, 18, 19, 20])
        close = _make_close_series([12, 13, 14, 15, 16, 17, 18, 19, 20, 21, 22])
        result = atr(high, low, close, 14)
        assert not result.empty


class TestRoundValue:
    def test_round(self):
        assert round_value(3.14159, 2) == 3.14

    def test_none(self):
        assert round_value(None) is None
