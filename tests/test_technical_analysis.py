"""Tests para el scoring de análisis técnico."""

from __future__ import annotations

import pandas as pd

from market_mcp.domain.models import Candle, PriceSeries
from market_mcp.services.technical_analysis import (
    TechnicalAnalysisService,
    _annualized_volatility,
    get_evaluation_capabilities,
)
from market_mcp.providers.symbol_resolution import SymbolResolver


class DummyTechnicalAnalysisService(TechnicalAnalysisService):
    def __init__(self, snapshots: dict[str, dict]):
        self.snapshots = snapshots

    def get_snapshot(self, symbol: str, period: str = "1y") -> dict:
        return self.snapshots[period]


def _snapshot(**overrides: object) -> dict:
    snapshot = {
        "symbol": "TEST",
        "price": 112.0,
        "indicators": {
            "sma20": 111.0,
            "sma50": 108.0,
            "sma100": 106.0,
            "sma200": 104.0,
            "rsi14": 58.0,
            "rsi14_prev": 56.0,
            "macd_histogram": 0.4,
            "macd_histogram_prev": 0.2,
            "atr14": 1.2,
        },
    }
    snapshot.update(overrides)
    return snapshot


class _CapturingProvider:
    def __init__(self) -> None:
        self.calls: list[tuple[object, object]] = []

    def get_history(self, symbol, start, end, interval="1d", adjusted=True):
        self.calls.append((start, end))
        timestamps = pd.date_range(end=pd.Timestamp.today(tz="UTC"), periods=220, freq="D")
        candles = [
            Candle(
                timestamp=timestamp.to_pydatetime(),
                open=float(100 + (index % 2)),
                high=float(101 + (index % 2)),
                low=float(99 + (index % 2)),
                close=float(100 + (index % 2)),
                adjusted_close=float(100 + (index % 2)),
                split_adjusted_close=float(100 + (index % 2)),
                distribution_adjusted_close=float(100 + (index % 2)),
            )
            for index, timestamp in enumerate(timestamps)
        ]
        return PriceSeries(symbol=symbol, candles=candles, data_quality="complete")

    def get_currency(self, symbol):
        return "USD"


class TestTechnicalAnalysisService:
    def test_fetch_includes_today_for_exclusive_provider_end_date(self):
        provider = _CapturingProvider()
        service = TechnicalAnalysisService(provider, SymbolResolver())

        result = service.get_snapshot("JPGL.L", "1y")

        assert result["indicators"]["rsi14"] is not None
        assert provider.calls[0][1] == pd.Timestamp.today().date() + pd.Timedelta(days=1)

    def test_fred_volatility_handles_series_crossing_zero(self):
        closes = pd.Series([-0.10, 0.0, 0.15, -0.05, 0.20])

        result = _annualized_volatility(closes, is_fred_observation=True)

        assert result is not None
        assert pd.notna(result)

    def test_evaluation_capabilities_expose_profiles_horizons_and_defaults(self):
        result = get_evaluation_capabilities()

        assert result["default_profile"] == "trend_standard"
        assert result["default_horizon"] == "medium_term"
        assert {item["name"] for item in result["profiles"]} == {
            "trend_standard",
            "trend_conservative",
            "low_volatility_accumulation",
            "low_volatility_distribution",
            "mean_reversion",
            "trend_weekly_etf",
            "auto",
        }
        assert {item["name"] for item in result["horizons"]} == {
            "short_term", "medium_term", "portfolio_monitor"
        }

    def test_distribution_profile_advertises_adjusted_series_and_no_extension(self):
        profiles = get_evaluation_capabilities()["profiles"]
        distribution = next(item for item in profiles if item["name"] == "low_volatility_distribution")

        assert distribution["price_mode"] == "distribution_adjusted"
        assert distribution["extension"]["enabled"] is False
        assert "RSI" not in distribution["indicators"]
        assert "MACD" not in distribution["indicators"]

    def test_profile_changes_horizon_and_state(self):
        service = DummyTechnicalAnalysisService(
            {
                "1y": _snapshot(
                    price=94.0,
                    indicators={
                        "sma20": 95.0,
                        "sma50": 96.0,
                        "sma100": 100.0,
                        "sma200": 110.0,
                        "rsi14": 40.0,
                        "rsi14_prev": 42.0,
                        "macd_histogram": -0.3,
                        "macd_histogram_prev": -0.2,
                        "atr14": 1.0,
                    },
                ),
                "2y": _snapshot(),
            }
        )

        short_term = service.evaluate_signal("TEST", profile="short_term")
        medium_term = service.evaluate_signal("TEST", profile="medium_term")

        assert short_term["profile"] == "short_term"
        assert medium_term["profile"] == "medium_term"
        assert short_term["technical_state"] != medium_term["technical_state"]
        assert short_term["entry_signal"] in {"BUY", "WAIT", "AVOID"}
        assert medium_term["position_signal"] in {"HOLD", "TRIM", "EXIT"}

    def test_bullish_extended_weakening_maps_to_avoid_trim(self):
        service = DummyTechnicalAnalysisService(
            {
                "2y": _snapshot(
                    price=130.0,
                    indicators={
                        "sma20": 125.0,
                        "sma50": 120.0,
                        "sma100": 115.0,
                        "sma200": 110.0,
                        "rsi14": 68.0,
                        "rsi14_prev": 72.0,
                        "macd_histogram": 0.3,
                        "macd_histogram_prev": 0.5,
                        "atr14": 1.0,
                    },
                )
            }
        )

        result = service.evaluate_signal("TEST", profile="medium_term")

        assert result["technical_state"] == "BULLISH_EXTENDED_WEAKENING"
        assert result["entry_signal"] == "AVOID"
        assert result["position_signal"] == "TRIM"

    def test_invalid_price_returns_error(self):
        service = DummyTechnicalAnalysisService({"2y": _snapshot(price=None)})

        result = service.evaluate_signal("TEST")

        assert result["error"] == "invalid_or_missing_price"
        assert result["profile"] == "medium_term"

    def test_supports_and_resistances_are_dynamic(self):
        service = DummyTechnicalAnalysisService(
            {
                "2y": _snapshot(
                    price=105.0,
                    indicators={
                        "sma20": 104.0,
                        "sma50": 100.0,
                        "sma100": 110.0,
                        "sma200": 95.0,
                        "rsi14": 50.0,
                        "rsi14_prev": 49.0,
                        "macd_histogram": 0.0,
                        "macd_histogram_prev": -0.1,
                        "atr14": 1.0,
                    },
                )
            }
        )

        result = service.evaluate_signal("TEST")

        assert result["levels"]["support_1"] == 104.0
        assert result["levels"]["support_2"] == 100.0
        assert result["levels"]["resistance_1"] == 110.0

    def test_low_volatility_accumulation_does_not_penalize_gradual_appreciation(self):
        service = DummyTechnicalAnalysisService({"2y": _snapshot(metrics={"drawdown_pct": -0.01, "volatility_pct": 1.0})})

        result = service.evaluate_signal("TEST", profile="low_volatility_accumulation", horizon="portfolio_monitor")

        assert result["technical_state"] == "BULLISH"
        assert result["entry_signal"] == "BUY"
        assert result["position_signal"] == "HOLD"
        assert result["metrics"]["extended"] is False

    def test_distribution_without_adjusted_series_is_not_classified_as_bearish(self):
        service = DummyTechnicalAnalysisService(
            {"2y": _snapshot(price=94.0, raw_price=94.0, indicators={
                "sma20": 95.0, "sma50": 96.0, "sma100": 100.0, "sma200": 110.0,
                "rsi14": 40.0, "atr14": 1.0,
            })}
        )

        result = service.evaluate_signal("TEST", profile="low_volatility_distribution", horizon="portfolio_monitor")

        assert result["technical_state"] == "NEUTRAL"
        assert result["confidence"] == "low"
        assert result["adjustment_data_available"] is False
        assert "Distribution-adjusted price series unavailable" in result["warnings"]

    def test_mean_reversion_uses_zscore_for_entry(self):
        service = DummyTechnicalAnalysisService(
            {"2y": _snapshot(price=100.0, metrics={"distance_zscore": -2.5}, indicators={
                "sma20": 102.0, "sma50": 105.0, "sma100": 106.0, "sma200": 107.0,
                "rsi14": 32.0, "atr14": 1.0,
            })}
        )

        result = service.evaluate_signal("TEST", profile="mean_reversion")

        assert result["technical_state"] == "BULLISH_PULLBACK"
        assert result["entry_signal"] == "BUY"

    def test_invalid_indicator_is_rejected(self):
        service = DummyTechnicalAnalysisService({"2y": _snapshot(indicators={"rsi14": 120.0})})

        result = service.evaluate_signal("TEST")

        assert result["error"] == "invalid_rsi"

    def test_weekly_etf_profile_requires_regime_and_accepts_rsi_up_to_68(self):
        snapshot = _snapshot(
            metrics={
                "trend_regime_score": 85,
                "weekly_ma_slopes_up": True,
                "timeframe": "weekly",
            },
            indicators={
                "sma20": 111.0,
                "sma50": 108.0,
                "sma100": 106.0,
                "sma200": 104.0,
                "rsi14": 68.0,
                "rsi14_prev": 66.0,
                "atr14": 2.0,
            },
        )
        service = DummyTechnicalAnalysisService({"5y": snapshot})

        result = service.evaluate_signal("TEST", profile="trend_weekly_etf")

        assert result["technical_state"] == "STRONG_BULLISH"
        assert result["entry_signal"] == "BUY"
        assert result["resolved_configuration"]["timeframe"] == "weekly"
        assert result["resolved_configuration"]["rsi_entry_max"] == 68

    def test_weekly_etf_waits_when_rsi_is_above_entry_threshold(self):
        service = DummyTechnicalAnalysisService(
            {
                "5y": _snapshot(
                    metrics={"trend_regime_score": 85, "weekly_ma_slopes_up": True, "timeframe": "weekly"},
                    indicators={
                        "sma20": 111.0, "sma50": 108.0, "sma100": 106.0, "sma200": 104.0,
                        "rsi14": 72.0, "rsi14_prev": 70.0, "atr14": 2.0,
                    },
                )
            }
        )

        result = service.evaluate_signal("TEST", profile="auto")

        assert result["technical_state"] == "BULLISH"
        assert result["entry_signal"] == "WAIT"
        assert result["profile"] == "auto"

    def test_weekly_etf_rejects_weak_regime_even_with_bullish_daily_shape(self):
        service = DummyTechnicalAnalysisService(
            {"5y": _snapshot(metrics={"trend_regime_score": 60, "weekly_ma_slopes_up": False, "timeframe": "weekly"})}
        )

        result = service.evaluate_signal("TEST", profile="trend_weekly_etf")

        assert result["technical_state"] == "NEUTRAL"
        assert result["entry_signal"] == "WAIT"
