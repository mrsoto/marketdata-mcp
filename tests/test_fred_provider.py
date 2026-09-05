"""Tests del proveedor FRED y su enrutamiento."""

from __future__ import annotations

from datetime import date
from unittest.mock import patch

from market_data.providers.composite import CompositeProvider
from market_data.providers.fred import FredProvider


class _Response:
    def __init__(self, payload: str) -> None:
        self.payload = payload.encode("utf-8")

    def __enter__(self) -> "_Response":
        return self

    def __exit__(self, *args: object) -> None:
        return None

    def read(self) -> bytes:
        return self.payload


def test_fred_provider_parses_values_and_missing_observations() -> None:
    payload = "observation_date,T10Y2Y\n2026-01-02,0.25\n2026-01-03,.\n2026-01-06,-0.10\n"

    with patch("market_data.providers.fred.urlopen", return_value=_Response(payload)) as request:
        series = FredProvider().get_history("T10Y2Y", date(2026, 1, 1), date(2026, 1, 7))

    assert request.call_args.args[0].startswith("https://fred.stlouisfed.org/graph/fredgraph.csv?")
    assert series.provider == "fred"
    assert series.series_kind == "fred_observation"
    assert [c.close for c in series.candles] == [0.25, -0.10]
    assert series.candles[0].timestamp.tzinfo is not None
    assert series.candles[0].open == series.candles[0].high == series.candles[0].low == 0.25


def test_fred_provider_returns_empty_for_unsupported_series() -> None:
    series = FredProvider().get_history("UNKNOWN", date(2026, 1, 1), date(2026, 1, 2))

    assert series.data_quality == "empty"
    assert series.provider == "fred"


def test_composite_provider_routes_fred_ids_and_explicit_prefix() -> None:
    fred = FredProvider()
    yahoo = object()
    provider = CompositeProvider(yahoo=yahoo, fred=fred)  # type: ignore[arg-type]

    assert provider._provider_for("DGS10") is fred
    assert provider._provider_for("FRED:T10YIE") is fred
    assert provider._provider_for("SPY") is yahoo
