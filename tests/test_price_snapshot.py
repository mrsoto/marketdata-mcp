"""Tests for price snapshot date boundaries."""

from __future__ import annotations

from datetime import date

import pandas as pd

from market_mcp.domain.models import Candle, PriceSeries
from market_mcp.services.price_snapshot import PriceSnapshotService


class _CapturingProvider:
    def __init__(self) -> None:
        self.calls: list[tuple[date, date]] = []

    def get_history(self, symbol, start, end, interval="1d", adjusted=True):
        self.calls.append((start, end))
        timestamp = pd.Timestamp("2026-08-26", tz="UTC").to_pydatetime()
        candle = Candle(
            timestamp=timestamp,
            open=1.0,
            high=2.0,
            low=1.0,
            close=1.5,
            adjusted_close=1.5,
        )
        return PriceSeries(symbol=symbol, candles=[candle], data_quality="complete")

    def get_currency(self, symbol):
        return "USD"


def test_fetch_includes_today_for_exclusive_provider_end_date():
    provider = _CapturingProvider()
    service = PriceSnapshotService(provider, resolver=None)

    service._fetch_series("JPGL.L", "1y")

    assert provider.calls[0][1] == date.today() + pd.Timedelta(days=1)
