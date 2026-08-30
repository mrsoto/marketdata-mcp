"""Enrutamiento entre FRED y Yahoo Finance."""

from __future__ import annotations

from datetime import date
from typing import Optional

from market_mcp.domain.models import PriceSeries
from market_mcp.providers.base import HistoricalPriceProvider
from market_mcp.providers.fred import FredProvider
from market_mcp.providers.yahoo import YahooProvider


class CompositeProvider(HistoricalPriceProvider):
    def __init__(self, yahoo: Optional[HistoricalPriceProvider] = None, fred: Optional[HistoricalPriceProvider] = None) -> None:
        self.yahoo = yahoo or YahooProvider()
        self.fred = fred or FredProvider()

    def _provider_for(self, symbol: str) -> HistoricalPriceProvider:
        return self.fred if FredProvider.supports_symbol(symbol) else self.yahoo

    def get_history(
        self,
        symbol: str,
        start: date,
        end: date,
        interval: str = "1d",
        adjusted: bool = True,
    ) -> PriceSeries:
        return self._provider_for(symbol).get_history(symbol, start, end, interval, adjusted)

    def get_currency(self, symbol: str) -> Optional[str]:
        return self._provider_for(symbol).get_currency(symbol)
