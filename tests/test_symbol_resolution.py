"""Tests para resolución de símbolos."""

from __future__ import annotations

from market_data.providers.symbol_resolution import (
    EXCHANGE_SUFFIX_MAP,
    UCITS_SUFFIX_FALLBACKS,
    _build_candidates,
)


class TestBuildCandidates:
    def test_simple_ticker(self):
        candidates = _build_candidates("VOO", include_ucits_fallbacks=False)
        assert candidates[0] == ("VOO", "original")

    def test_colon_suffix_maps(self):
        candidates = _build_candidates("JPGL:GB", include_ucits_fallbacks=False)
        methods = [m for _, m in candidates]
        assert "map_colon_GB_to_suffix" in methods
        jpgl_l = [c for c, _ in candidates if c == "JPGL.L"]
        assert len(jpgl_l) == 1

    def test_ucits_fallbacks(self):
        candidates = _build_candidates("CSKR", include_ucits_fallbacks=True)
        methods = [m for _, m in candidates]
        assert any("ucits_suffix" in m for m in methods)
        csKR_L = [c for c, _ in candidates if c == "CSKR.L"]
        assert len(csKR_L) == 1

    def test_dot_suffix_dropped(self):
        candidates = _build_candidates("CSKR.L", include_ucits_fallbacks=False)
        methods = [m for _, m in candidates]
        assert "drop_dot_suffix" in methods
        csKR = [c for c, _ in candidates if c == "CSKR"]
        assert len(csKR) == 1

    def test_empty_symbol(self):
        candidates = _build_candidates("", include_ucits_fallbacks=False)
        assert len(candidates) == 0


class TestExchangeSuffixMap:
    def test_gb_maps_to_L(self):
        assert EXCHANGE_SUFFIX_MAP["GB"] == ".L"

    def test_us_maps_to_empty(self):
        assert EXCHANGE_SUFFIX_MAP["US"] == ""

    def test_de_maps_to_DE(self):
        assert EXCHANGE_SUFFIX_MAP["DE"] == ".DE"


class TestUCITSFallbacks:
    def test_has_common_suffixes(self):
        assert ".L" in UCITS_SUFFIX_FALLBACKS
        assert ".DE" in UCITS_SUFFIX_FALLBACKS
