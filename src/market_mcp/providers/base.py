"""Protocolo base para proveedores de datos históricos."""

from __future__ import annotations

from abc import ABC, abstractmethod
from datetime import date
from typing import Optional

from market_mcp.domain.models import PriceSeries


class HistoricalPriceProvider(ABC):
    @abstractmethod
    def get_history(
        self,
        symbol: str,
        start: date,
        end: date,
        interval: str = "1d",
        adjusted: bool = True,
    ) -> PriceSeries:
        ...

    @abstractmethod
    def get_currency(self, symbol: str) -> Optional[str]:
        ...
