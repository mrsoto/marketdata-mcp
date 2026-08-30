"""Proveedor FRED para series económicas diarias."""

from __future__ import annotations

import csv
import io
import logging
from datetime import date, datetime, timezone
from typing import Optional
from urllib.parse import urlencode
from urllib.request import urlopen

import pandas as pd

from market_mcp.domain.models import Candle, PriceSeries
from market_mcp.providers.base import HistoricalPriceProvider

logger = logging.getLogger(__name__)

FRED_GRAPH_URL = "https://fred.stlouisfed.org/graph/fredgraph.csv"
FRED_SERIES_IDS = frozenset({"T10YIE", "DFII10", "DGS10", "DGS2", "T10Y2Y", "DTWEXBGS"})


def _safe_value(value: str) -> Optional[float]:
    if not value or value == ".":
        return None
    try:
        result = float(value)
    except ValueError:
        return None
    return None if pd.isna(result) else result


class FredProvider(HistoricalPriceProvider):
    def __init__(self, timeout: float = 20.0) -> None:
        self.timeout = timeout

    @staticmethod
    def normalize_symbol(symbol: str) -> str:
        normalized = symbol.strip().upper()
        return normalized.removeprefix("FRED:")

    @classmethod
    def supports_symbol(cls, symbol: str) -> bool:
        return cls.normalize_symbol(symbol) in FRED_SERIES_IDS

    def get_history(
        self,
        symbol: str,
        start: date,
        end: date,
        interval: str = "1d",
        adjusted: bool = True,
    ) -> PriceSeries:
        series_id = self.normalize_symbol(symbol)
        empty = PriceSeries(
            symbol=symbol,
            interval=interval,
            provider="fred",
            series_kind="fred_observation",
            price_adjustment="raw",
            data_quality="empty",
        )
        if not self.supports_symbol(symbol) or interval != "1d":
            return empty

        query = urlencode({"id": series_id, "cosd": start.isoformat(), "coed": end.isoformat()})
        try:
            with urlopen(f"{FRED_GRAPH_URL}?{query}", timeout=self.timeout) as response:
                payload = response.read().decode("utf-8")
        except Exception as exc:
            logger.warning("FRED download failed for %s: %s", series_id, exc)
            return empty

        candles: list[Candle] = []
        try:
            for row in csv.DictReader(io.StringIO(payload)):
                value = _safe_value((row.get(series_id) or row.get("VALUE") or "").strip())
                if value is None:
                    continue
                date_value = row.get("DATE") or row.get("observation_date")
                if not date_value:
                    raise KeyError("DATE")
                timestamp = datetime.strptime(date_value, "%Y-%m-%d").replace(tzinfo=timezone.utc)
                candles.append(
                    Candle(
                        timestamp=timestamp,
                        open=value,
                        high=value,
                        low=value,
                        close=value,
                        adjusted_close=value,
                        split_adjusted_close=value,
                        distribution_adjusted_close=value,
                    )
                )
        except (KeyError, ValueError, TypeError) as exc:
            logger.warning("Invalid FRED response for %s: %s", series_id, exc)
            return empty

        candles.sort(key=lambda candle: candle.timestamp)
        return PriceSeries(
            symbol=symbol,
            interval=interval,
            candles=candles,
            provider="fred",
            series_kind="fred_observation",
            price_adjustment="raw",
            data_quality="complete" if candles else "empty",
        )

    def get_currency(self, symbol: str) -> Optional[str]:
        return None
