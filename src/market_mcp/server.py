"""Servidor MCP principal con FastMCP."""

from __future__ import annotations

import os
from pathlib import Path
from typing import List, Literal, Optional

from mcp.server.fastmcp import FastMCP

from market_mcp.domain.models import (
    ETFPriceSnapshotReport,
    IndicatorSnapshot,
    SymbolResolution,
)
from market_mcp.providers.composite import CompositeProvider
from market_mcp.providers.symbol_resolution import SymbolResolver
from market_mcp.services.price_snapshot import PriceSnapshotService
from market_mcp.services.maritime_chokepoints import MaritimeChokepointService
from market_mcp.services.technical_analysis import TechnicalAnalysisService
from market_mcp.storage.cache import PriceCache, SnapshotCache
from market_mcp.storage.equivalence_registry import EquivalenceRegistry

DATA_DIR = Path(os.environ.get("MARKET_MCP_DATA_DIR", "data"))

EQUIVALENCE_REGISTRY_PATH = Path(
    os.environ.get("MARKET_MCP_EQUIVALENCE_REGISTRY_PATH", DATA_DIR / "yahoo_ticker_equivalence_registry.json")
)
TICKER_MEMORY_PATH = Path(
    os.environ.get("MARKET_MCP_TICKER_MEMORY_PATH", DATA_DIR / "yahoo_ticker_memory.json")
)
OHLCV_CACHE_DIR = Path(
    os.environ.get("MARKET_MCP_OHLCV_CACHE_DIR", DATA_DIR / "ohlcv_cache")
)
SNAPSHOT_CACHE_DIR = Path(
    os.environ.get("MARKET_MCP_SNAPSHOT_CACHE_DIR", DATA_DIR / "snapshot_cache")
)

mcp = FastMCP("market-analysis")

provider = CompositeProvider()
equivalence_registry = EquivalenceRegistry(
    registry_path=EQUIVALENCE_REGISTRY_PATH,
    memory_map_path=TICKER_MEMORY_PATH,
)
resolver = SymbolResolver(registry=equivalence_registry)
price_cache = PriceCache(cache_dir=OHLCV_CACHE_DIR, ttl_seconds=21600)
snapshot_cache = SnapshotCache(cache_dir=SNAPSHOT_CACHE_DIR, ttl_seconds=3600)

price_snapshot_service = PriceSnapshotService(
    provider=provider,
    resolver=resolver,
    price_cache=price_cache,
    snapshot_cache=snapshot_cache,
)
technical_service = TechnicalAnalysisService(
    provider=provider,
    resolver=resolver,
    price_cache=price_cache,
)
maritime_service = MaritimeChokepointService()


# --- Tools de equivalencias ---


@mcp.tool()
def register_ticker_equivalence(
    original_ticker: str,
    selected_yahoo_ticker: str,
    source: str = "manual",
    source_symbol: Optional[str] = None,
    reason: Optional[str] = None,
) -> dict:
    """Registra una equivalencia de símbolo Yahoo de forma persistente."""
    from market_mcp.tools.symbols import register_equivalence as _register
    return _register(
        registry=equivalence_registry,
        original_ticker=original_ticker,
        selected_yahoo_ticker=selected_yahoo_ticker,
        source=source,
        source_symbol=source_symbol,
        reason=reason,
    )


@mcp.tool()
def list_ticker_equivalences(
    limit: int = 50,
    status_filter: Optional[str] = None,
) -> dict:
    """Lista equivalencias de símbolos registradas."""
    from market_mcp.tools.symbols import list_equivalences as _list
    return _list(registry=equivalence_registry, limit=limit, status_filter=status_filter)


@mcp.tool()
def get_ticker_equivalence(
    original_ticker: str,
) -> dict:
    """Consulta si existe una equivalencia conocida para un símbolo."""
    from market_mcp.tools.symbols import get_equivalence as _get
    return _get(registry=equivalence_registry, original_ticker=original_ticker)


# --- Tools de precios ---


@mcp.tool()
def get_etf_price_snapshot(
    symbol: str,
    period: str = "2y",
    include_note: bool = True,
) -> dict:
    """Obtiene snapshot con indicadores; admite IDs FRED como FRED:T10YIE."""
    from market_mcp.tools.prices import get_etf_price_snapshot as _snapshot
    return _snapshot(
        service=price_snapshot_service,
        symbol=symbol,
        period=period,
        include_note=include_note,
    )


@mcp.tool()
def get_multiple_etf_price_snapshots(
    symbols: List[str],
    period: str = "2y",
) -> dict:
    """Obtiene snapshots para múltiples símbolos, incluidos IDs FRED con prefijo FRED:."""
    from market_mcp.tools.prices import get_multiple_etf_price_snapshots as _multi
    return _multi(service=price_snapshot_service, symbols=symbols, period=period)


@mcp.tool()
def get_price_history(
    symbol: str,
    period: str = "1y",
    max_points: int = 300,
) -> dict:
    """Obtiene historial normalizado; admite FRED:T10YIE, DFII10, DGS10, DGS2, T10Y2Y y DTWEXBGS."""
    from market_mcp.tools.prices import get_price_history as _history
    return _history(service=technical_service, symbol=symbol, period=period, max_points=max_points)


@mcp.tool()
def get_technical_snapshot(
    symbol: str,
    period: str = "1y",
) -> dict:
    """Obtiene snapshot técnico completo; admite series FRED con el prefijo FRED:."""
    from market_mcp.tools.prices import get_technical_snapshot as _tech
    return _tech(service=technical_service, symbol=symbol, period=period)


@mcp.tool()
def get_technical_evaluation_capabilities() -> dict:
    """Lista perfiles y horizontes tecnicos disponibles para seleccionar."""
    from market_mcp.tools.prices import get_technical_evaluation_capabilities as _capabilities
    return _capabilities()


@mcp.tool()
def evaluate_technical_signal(
    symbol: str,
    profile: Literal["trend_standard", "trend_conservative", "low_volatility_accumulation", "low_volatility_distribution", "mean_reversion", "trend_weekly_etf", "auto"] = "trend_standard",
    horizon: Literal["short_term", "medium_term", "portfolio_monitor"] = "medium_term",
    include_evidence: bool = True,
) -> dict:
    """Evalúa señal técnica; también admite series macro FRED usando FRED:<id>."""
    from market_mcp.tools.prices import evaluate_technical_signal as _eval
    return _eval(service=technical_service, symbol=symbol, profile=profile, horizon=horizon, include_evidence=include_evidence)


@mcp.tool()
def compare_technical_snapshots(
    symbols: List[str],
    profile: Literal["trend_standard", "trend_conservative", "low_volatility_accumulation", "low_volatility_distribution", "mean_reversion", "trend_weekly_etf", "auto"] = "trend_standard",
    horizon: Literal["short_term", "medium_term", "portfolio_monitor"] = "medium_term",
) -> dict:
    """Compara snapshots técnicos, incluidos símbolos FRED con prefijo FRED:."""
    from market_mcp.tools.prices import compare_technical_snapshots as _compare
    return _compare(service=technical_service, symbols=symbols, profile=profile, horizon=horizon)


@mcp.tool()
def get_maritime_chokepoint_status(
    chokepoint: Literal["hormuz", "bab_el_mandeb", "both"] = "both",
    include_history: bool = True,
) -> dict:
    """Consulta tránsito AIS de PortWatch para Ormuz y Bab el-Mandeb."""
    from market_mcp.tools.maritime import get_maritime_chokepoint_status as _status
    return _status(service=maritime_service, chokepoint=chokepoint, include_history=include_history)


# --- Tool de bootstrap ---


@mcp.tool()
def bootstrap_cache_from_external(
    source_dir: str,
    target_cache_dir: str = "data/ohlcv_cache",
    dry_run: bool = False,
) -> dict:
    """Import OHLCV cache from an external directory (for example the external cache path)."""
    from market_mcp.tools.bootstrap import bootstrap_cache_from_external as _bootstrap
    return _bootstrap(source_dir=source_dir, target_cache_dir=target_cache_dir, dry_run=dry_run)


def main() -> None:
    mcp.run(transport="stdio")


if __name__ == "__main__":
    main()
