"""Resolución de símbolos con fallback por exchange y equivalentes conocidas."""

from __future__ import annotations

from typing import Dict, List, Optional, Tuple

from market_mcp.domain.models import SymbolResolution
from market_mcp.storage.equivalence_registry import EquivalenceRegistry

EXCHANGE_SUFFIX_MAP: Dict[str, str] = {
    "GB": ".L",
    "LN": ".L",
    "LSE": ".L",
    "UK": ".L",
    "US": "",
    "ARCA": "",
    "NYSE": "",
    "NASDAQ": "",
    "DE": ".DE",
    "XETRA": ".DE",
    "PA": ".PA",
    "FP": ".PA",
    "MI": ".MI",
    "IM": ".MI",
    "AS": ".AS",
    "NA": ".AS",
    "SW": ".SW",
    "VX": ".SW",
}

UCITS_SUFFIX_FALLBACKS = [".L", ".DE", ".MI", ".AS", ".PA", ".SW"]


def _build_candidates(raw: str, include_ucits_fallbacks: bool = True) -> List[Tuple[str, str]]:
    candidates: List[Tuple[str, str]] = []
    seen: set[str] = set()

    def add(sym: str, reason: str) -> None:
        s = sym.upper().strip()
        if not s or s in seen:
            return
        seen.add(s)
        candidates.append((s, reason))

    add(raw, "original")

    if ":" in raw:
        base, venue = raw.split(":", 1)
        add(base, "drop_colon_suffix")
        mapped = EXCHANGE_SUFFIX_MAP.get(venue.upper())
        if mapped is not None:
            candidate = base + mapped
            if candidate != base:
                add(candidate, f"map_colon_{venue}_to_suffix")

    if "." in raw:
        add(raw.split(".", 1)[0], "drop_dot_suffix")

    if include_ucits_fallbacks:
        base = raw.split(":", 1)[0].split(".", 1)[0]
        for suffix in UCITS_SUFFIX_FALLBACKS:
            candidate = base + suffix
            if candidate != base:
                add(candidate, f"ucits_suffix_{suffix}")

    return candidates


class SymbolResolver:
    def __init__(self, registry: Optional[EquivalenceRegistry] = None) -> None:
        self.registry = registry

    def try_resolve(
        self,
        symbol: str,
        test_fn,
        include_ucits_fallbacks: bool = True,
    ) -> SymbolResolution:
        raw = symbol.strip().upper()
        if not raw:
            return SymbolResolution(
                query_symbol=symbol,
                original_symbol=raw,
                used_equivalent=False,
                failed=True,
                failure_reason="empty_symbol",
            )

        candidates = _build_candidates(raw, include_ucits_fallbacks)

        if self.registry is not None:
            known = self.registry.lookup(raw)
            if known and known.upper() != raw:
                candidates.insert(1, (known, "equivalence_registry"))

        tried: List[str] = []
        for candidate, method in candidates:
            tried.append(candidate)
            result = test_fn(candidate)
            if result:
                used_eq = candidate != raw
                note = None
                if used_eq:
                    note = f"Used equivalent symbol {candidate} instead of original {raw} (method: {method})"
                return SymbolResolution(
                    query_symbol=symbol,
                    original_symbol=raw,
                    resolved_symbol=candidate,
                    used_equivalent=used_eq,
                    resolution_method=method,
                    candidates_tried=tried,
                    failed=False,
                    note=note,
                )

        return SymbolResolution(
            query_symbol=symbol,
            original_symbol=raw,
            used_equivalent=False,
            failed=True,
            candidates_tried=tried,
            failure_reason="all_candidates_failed",
        )

    def resolve(self, symbol: str, test_fn) -> SymbolResolution:
        return self.try_resolve(symbol, test_fn)
