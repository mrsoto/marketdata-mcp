"""Tools MCP para consulta de precios con fallback de equivalentes."""

from __future__ import annotations

from typing import List, Literal, Optional

from market_data.services.price_snapshot import PriceSnapshotService
from market_data.services.technical_analysis import TechnicalAnalysisService, get_evaluation_capabilities
from market_data.domain.models import is_valid_price_series


def get_technical_evaluation_capabilities() -> dict:
    """Describe the profiles and horizons available to the calling agent."""
    return get_evaluation_capabilities()


def get_etf_price_snapshot(
    service: PriceSnapshotService,
    symbol: str,
    period: str = "2y",
    include_note: bool = True,
) -> dict:
    report = service.get_etf_price_snapshot(symbol=symbol, period=period, include_note=include_note)
    return report.model_dump(mode="json")


def get_multiple_etf_price_snapshots(
    service: PriceSnapshotService,
    symbols: List[str],
    period: str = "2y",
) -> dict:
    reports = []
    for sym in symbols:
        report = service.get_etf_price_snapshot(symbol=sym, period=period)
        reports.append(report.model_dump(mode="json"))
    return {"count": len(reports), "snapshots": reports}


def get_price_history(
    service: TechnicalAnalysisService,
    symbol: str,
    period: str = "1y",
    max_points: int = 300,
) -> dict:
    resolution = service.resolver.try_resolve(symbol, service._check_symbol)
    if resolution.failed:
        return {
            "symbol": symbol,
            "error": "missing_data" if resolution.failure_reason == "all_candidates_failed" else resolution.failure_reason,
            "candidates_tried": resolution.candidates_tried,
        }

    resolved = resolution.resolved_symbol or resolution.original_symbol
    series = service._fetch_series(resolved, period, True)

    if not is_valid_price_series(series):
        return {
            "symbol": resolved,
            "error": "missing_data" if series.data_quality == "missing" else "no_data",
            "original_symbol": resolution.original_symbol,
            "used_equivalent": resolution.used_equivalent,
            "resolution_method": resolution.resolution_method,
            "candidates_tried": resolution.candidates_tried,
        }

    candles = [c.to_dict() for c in series.candles[-max_points:]]

    return {
        "symbol": resolved,
        "currency": series.currency,
        "provider": series.provider,
        "series_kind": series.series_kind,
        "original_symbol": resolution.original_symbol,
        "used_equivalent": resolution.used_equivalent,
        "resolution_method": resolution.resolution_method,
        "candles_count": len(candles),
        "candles": candles,
    }


def get_technical_snapshot(
    service: TechnicalAnalysisService,
    symbol: str,
    period: str = "1y",
) -> dict:
    return service.get_snapshot(symbol=symbol, period=period)


def evaluate_technical_signal(
    service: TechnicalAnalysisService,
    symbol: str,
    profile: Literal["trend_standard", "trend_conservative", "low_volatility_accumulation", "low_volatility_distribution", "mean_reversion", "trend_weekly_etf", "auto"] = "trend_standard",
    horizon: Literal["short_term", "medium_term", "portfolio_monitor"] = "medium_term",
    include_evidence: bool = True,
) -> dict:
    return service.evaluate_signal(symbol=symbol, profile=profile, horizon=horizon, include_evidence=include_evidence)


def compare_technical_snapshots(
    service: TechnicalAnalysisService,
    symbols: List[str],
    profile: Literal["trend_standard", "trend_conservative", "low_volatility_accumulation", "low_volatility_distribution", "mean_reversion", "trend_weekly_etf", "auto"] = "trend_standard",
    horizon: Literal["short_term", "medium_term", "portfolio_monitor"] = "medium_term",
) -> dict:
    results = service.compare_snapshots(symbols=symbols, profile=profile, horizon=horizon)
    return {"count": len(results), "results": results}
