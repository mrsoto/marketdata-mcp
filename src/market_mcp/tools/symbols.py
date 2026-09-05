"""Tools MCP para registro y consulta de equivalencias de símbolos."""

from __future__ import annotations

from typing import Optional

from market_data.storage.equivalence_registry import EquivalenceRegistry


def register_equivalence(
    registry: EquivalenceRegistry,
    original_ticker: str,
    selected_yahoo_ticker: str,
    source: str = "manual",
    source_symbol: Optional[str] = None,
    reason: Optional[str] = None,
) -> dict:
    result = registry.register(
        original_ticker=original_ticker,
        selected_yahoo_ticker=selected_yahoo_ticker,
        source=source,
        source_symbol=source_symbol,
        reason=reason,
    )
    return {
        "created": result["created"],
        "original_ticker": original_ticker,
        "selected_yahoo_ticker": selected_yahoo_ticker,
        "memory_updated": result["memory_updated"],
        "entry_count": result["registry_entry_count"],
    }


def list_equivalences(
    registry: EquivalenceRegistry,
    limit: int = 50,
    status_filter: Optional[str] = None,
) -> dict:
    entries = registry.list_entries(limit=limit, status_filter=status_filter)
    return {
        "count": len(entries),
        "entries": entries,
    }


def get_equivalence(
    registry: EquivalenceRegistry,
    original_ticker: str,
) -> dict:
    resolved = registry.lookup(original_ticker)
    return {
        "original_ticker": original_ticker,
        "resolved_ticker": resolved,
        "found": resolved is not None,
    }
