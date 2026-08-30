"""Deterministic technical evaluation for configurable time-series profiles."""

from __future__ import annotations

import math
from datetime import date, timedelta
from typing import Any, Dict, List, Literal, Optional, Tuple, TypedDict

import pandas as pd

from market_mcp.domain.indicators import atr, macd, rsi, round_value, sma
from market_mcp.domain.models import PriceSeries, is_valid_price_series
from market_mcp.providers.base import HistoricalPriceProvider
from market_mcp.providers.symbol_resolution import SymbolResolver
from market_mcp.storage.cache import PriceCache

EvaluationProfile = Literal[
    "trend_standard", "trend_conservative", "low_volatility_accumulation",
    "low_volatility_distribution", "mean_reversion", "trend_weekly_etf", "auto",
]
SignalHorizon = Literal["short_term", "medium_term", "portfolio_monitor"]
TechnicalState = Literal[
    "STRONG_BULLISH", "BULLISH", "BULLISH_PULLBACK", "BULLISH_EXTENDED",
    "BULLISH_EXTENDED_WEAKENING", "NEUTRAL", "BEARISH_REVERSAL_ATTEMPT",
    "BEARISH", "STRONG_BEARISH",
]
EntrySignal = Literal["BUY", "WAIT", "AVOID"]
PositionSignal = Literal["HOLD", "TRIM", "EXIT"]


class SignalEvaluation(TypedDict, total=False):
    symbol: str
    provider: str
    series_kind: str
    profile: str
    horizon: SignalHorizon
    technical_state: TechnicalState
    entry_signal: EntrySignal
    position_signal: PositionSignal
    score: int
    confidence: Literal["low", "medium", "high"]
    indicator_coverage: float
    requested_price_mode: str
    resolved_price_mode: str
    adjustment_data_available: bool
    metrics: dict
    technical_metrics: dict
    score_components: dict
    levels: dict
    reasons: list[str]
    warnings: list[str]
    resolved_configuration: dict


PROFILE_CONFIG: dict[str, dict[str, Any]] = {
    "trend_standard": {"price_mode": "split_adjusted", "use_ma_alignment": True, "use_rsi": True, "use_macd": True, "use_atr": True, "extension": {"enabled": True, "method": "atr", "reference": "sma50"}, "weights": {"trend": .40, "momentum": .30, "extension": .20, "stability": .10, "drawdown": 0}},
    "trend_conservative": {"price_mode": "split_adjusted", "use_ma_alignment": True, "use_rsi": True, "use_macd": True, "use_atr": True, "extension": {"enabled": True, "method": "atr", "reference": "sma100"}, "weights": {"trend": .60, "momentum": .15, "extension": .10, "stability": .10, "drawdown": .05}},
    "low_volatility_accumulation": {"price_mode": "split_adjusted", "use_ma_alignment": False, "use_rsi": False, "use_macd": False, "use_atr": True, "extension": {"enabled": False, "method": "none"}, "weights": {"trend": .30, "momentum": 0, "extension": 0, "stability": .40, "drawdown": .30}},
    "low_volatility_distribution": {"price_mode": "distribution_adjusted", "use_ma_alignment": False, "use_rsi": False, "use_macd": False, "use_atr": True, "extension": {"enabled": False, "method": "none"}, "weights": {"trend": .25, "momentum": 0, "extension": 0, "stability": .35, "drawdown": .25, "abnormal_gap": .15}},
    "mean_reversion": {"price_mode": "split_adjusted", "use_ma_alignment": False, "use_rsi": True, "use_macd": False, "use_atr": True, "extension": {"enabled": True, "method": "zscore", "reference": "sma50"}, "weights": {"trend": .15, "momentum": .25, "extension": .40, "stability": .10, "drawdown": .10}},
    "trend_weekly_etf": {"price_mode": "split_adjusted", "timeframe": "weekly", "history_period": "5y", "use_ma_alignment": True, "use_rsi": True, "use_macd": False, "use_atr": True, "extension": {"enabled": False, "method": "none"}, "weights": {"trend": .65, "momentum": 0, "extension": 0, "stability": .10, "drawdown": .25}, "minimum_regime_score": 70, "rsi_entry_max": 68},
}
HORIZON_CONFIG: dict[str, dict[str, Any]] = {
    "short_term": {"history_period": "1y", "confirmation_days": 1, "trend_sensitivity": "high", "momentum_sensitivity": "high", "structural_sensitivity": "low"},
    "medium_term": {"history_period": "2y", "confirmation_days": 3, "trend_sensitivity": "medium", "momentum_sensitivity": "medium", "structural_sensitivity": "medium"},
    "portfolio_monitor": {"history_period": "2y", "confirmation_days": 5, "trend_sensitivity": "low", "momentum_sensitivity": "low", "structural_sensitivity": "high"},
}
PROFILE_METADATA: dict[str, dict[str, Any]] = {
    "trend_standard": {
        "description": "Perfil tendencial general para series con volatilidad normal.",
        "best_for": "Series con tendencia y comportamiento tecnico convencional.",
        "entry_behavior": "Compra tendencias confirmadas o pullbacks y evita entradas extendidas.",
    },
    "trend_conservative": {
        "description": "Perfil tendencial con mayor peso estructural y menor sensibilidad al ruido.",
        "best_for": "Analisis de posiciones que requieren confirmacion lenta.",
        "entry_behavior": "Prioriza la tendencia de largo plazo y retrasa cambios tacticos.",
    },
    "low_volatility_accumulation": {
        "description": "Perfil para apreciacion gradual con volatilidad y drawdown reducidos.",
        "best_for": "Series estables sin discontinuidades economicas esperadas.",
        "entry_behavior": "No penaliza permanecer sobre medias ni exige una correccion para entrar.",
    },
    "low_volatility_distribution": {
        "description": "Perfil para series estables con discontinuidades periodicas corregibles por distribuciones.",
        "best_for": "Series cuya continuidad economica debe analizarse sobre precios ajustados por distribucion.",
        "entry_behavior": "Ignora gaps de distribucion cuando desaparecen en la serie ajustada.",
    },
    "mean_reversion": {
        "description": "Perfil que prioriza desviaciones anormales respecto a una referencia y su reversion.",
        "best_for": "Series donde la distancia a la media es mas informativa que la persistencia tendencial.",
        "entry_behavior": "Busca desviaciones negativas confirmadas y evita comprar desviaciones positivas.",
    },
    "trend_weekly_etf": {
        "description": "Perfil semanal para ETFs con tendencia persistente y RSI estructuralmente elevado.",
        "best_for": "ETFs que permanecen sobre sus medias durante meses y mantienen momentum positivo.",
        "entry_behavior": "Compra estructura semanal ascendente con RSI14 semanal hasta 68; no exige una correccion diaria.",
    },
}
HORIZON_METADATA: dict[str, dict[str, str]] = {
    "short_term": {"description": "Reacciona rapidamente a cambios tacticos y momentum.", "sensitivity": "high"},
    "medium_term": {"description": "Equilibra tendencia estructural y momentum.", "sensitivity": "medium"},
    "portfolio_monitor": {"description": "Reduce el ruido y exige mayor persistencia estructural.", "sensitivity": "low"},
}
_LEGACY = {"short_term": ("trend_standard", "short_term"), "medium_term": ("trend_standard", "medium_term"), "portfolio_monitor": ("trend_conservative", "portfolio_monitor")}
STATE_SIGNAL_MAP: dict[str, Tuple[EntrySignal, PositionSignal]] = {
    "STRONG_BULLISH": ("BUY", "HOLD"), "BULLISH": ("WAIT", "HOLD"), "BULLISH_PULLBACK": ("BUY", "HOLD"),
    "BULLISH_EXTENDED": ("WAIT", "HOLD"), "BULLISH_EXTENDED_WEAKENING": ("AVOID", "TRIM"), "NEUTRAL": ("WAIT", "HOLD"),
    "BEARISH_REVERSAL_ATTEMPT": ("WAIT", "TRIM"), "BEARISH": ("AVOID", "TRIM"), "STRONG_BEARISH": ("AVOID", "EXIT"),
}
PROFILE_SIGNAL_OVERRIDES = {
    "low_volatility_accumulation": {"BULLISH": ("BUY", "HOLD"), "STRONG_BULLISH": ("BUY", "HOLD")},
    "low_volatility_distribution": {"BULLISH": ("BUY", "HOLD"), "STRONG_BULLISH": ("BUY", "HOLD")},
}


def get_evaluation_capabilities() -> dict[str, Any]:
    """Return the public catalog of profiles and horizons available to agents."""
    profiles = []
    for name, config in PROFILE_CONFIG.items():
        indicators = ["SMA20", "SMA50", "SMA100", "SMA200"]
        if config["use_rsi"]:
            indicators.append("RSI")
        if config["use_macd"]:
            indicators.append("MACD")
        if config["use_atr"]:
            indicators.append("ATR")
        profiles.append({
            "name": name,
            **PROFILE_METADATA[name],
            "price_mode": config["price_mode"],
            "indicators": indicators,
            "use_ma_alignment": config["use_ma_alignment"],
            "extension": {
                "enabled": config["extension"]["enabled"],
                "method": config["extension"]["method"],
                "reference": config["extension"].get("reference"),
            },
        })
    profiles.append({
        "name": "auto",
        "description": "Seleccion automatica del regimen tendencial semanal para ETFs.",
        "best_for": "Activos cuyo comportamiento no se quiere clasificar manualmente por simbolo.",
        "entry_behavior": "Aplica la estrategia semanal solo cuando el score de regimen supera el umbral.",
        "price_mode": "split_adjusted",
        "indicators": ["SMA20", "SMA50", "SMA100", "SMA200", "RSI"],
        "use_ma_alignment": True,
        "extension": {"enabled": False, "method": "none", "reference": None},
    })
    horizons = []
    for name, config in HORIZON_CONFIG.items():
        horizons.append({
            "name": name,
            **HORIZON_METADATA[name],
            "history_period": config["history_period"],
            "confirmation_days": config["confirmation_days"],
            "trend_sensitivity": config["trend_sensitivity"],
            "momentum_sensitivity": config["momentum_sensitivity"],
            "structural_sensitivity": config["structural_sensitivity"],
        })
    return {
        "default_profile": "trend_standard",
        "default_horizon": "medium_term",
        "profiles": profiles,
        "horizons": horizons,
    }


class InvalidMarketDataError(ValueError):
    pass


def _valid(value: object) -> bool:
    try:
        return value is not None and math.isfinite(float(value))
    except (TypeError, ValueError):
        return False


def _number(value: object) -> Optional[float]:
    return float(value) if _valid(value) else None


def _annualized_volatility(closes: pd.Series, is_fred_observation: bool) -> Optional[float]:
    changes = closes.diff() if is_fred_observation else closes.pct_change()
    changes = changes.dropna()
    changes = changes[changes.map(_valid)]
    if len(changes) <= 1:
        return None
    return float(changes.std() * math.sqrt(252) * (1 if is_fred_observation else 100))


def _last_two(values: pd.Series) -> Tuple[Optional[float], Optional[float]]:
    clean = [float(v) for v in values.dropna() if _valid(v)]
    return (clean[-1], clean[-2]) if len(clean) > 1 else ((clean[-1], None) if clean else (None, None))


def _alignment(values: list[Optional[float]], bullish: bool) -> bool:
    return all(v is not None for v in values) and all((values[i] > values[i + 1]) if bullish else (values[i] < values[i + 1]) for i in range(3))


class TechnicalAnalysisService:
    def __init__(self, provider: HistoricalPriceProvider, resolver: SymbolResolver, price_cache: Optional[PriceCache] = None) -> None:
        self.provider, self.resolver, self.price_cache = provider, resolver, price_cache

    def _fetch_series(self, symbol: str, period: str, adjusted: bool = True) -> PriceSeries:
        if self.price_cache is not None:
            cached = self.price_cache.get(symbol, "1d", period, adjusted)
            if cached is not None and is_valid_price_series(cached):
                return cached
        days = {"1mo": 30, "3mo": 91, "6mo": 182, "1y": 365, "2y": 730, "3y": 1095, "5y": 1825}.get(period, 365)
        # Yahoo's end date is exclusive; include today's completed session by
        # using tomorrow as the upper bound.
        today = date.today()
        end = today + timedelta(days=1)
        series = self.provider.get_history(symbol, today - timedelta(days=days), end, "1d", adjusted)
        if self.price_cache is not None and is_valid_price_series(series):
            self.price_cache.set(symbol, "1d", period, adjusted, series)
        return series

    def _check_symbol(self, symbol: str) -> bool:
        series = self._fetch_series(symbol, "3mo", True)
        return is_valid_price_series(series)

    def get_snapshot(self, symbol: str, period: str = "1y", price_mode: str = "split_adjusted", timeframe: str = "daily") -> Dict:
        resolution = self.resolver.try_resolve(symbol, self._check_symbol)
        if resolution.failed:
            return {"symbol": symbol, "error": "missing_data" if resolution.failure_reason == "all_candidates_failed" else resolution.failure_reason or "all_candidates_failed", "candidates_tried": resolution.candidates_tried}
        resolved = resolution.resolved_symbol or resolution.original_symbol
        series = self._fetch_series(resolved, period, True)
        if not is_valid_price_series(series):
            return {"symbol": resolved, "error": "missing_data" if series.data_quality == "missing" else "no_data"}
        timestamps = [c.timestamp for c in series.candles]
        if timestamps != sorted(timestamps) or len(set(timestamps)) != len(timestamps):
            return {"symbol": resolved, "error": "invalid_time_series"}
        is_fred_observation = series.series_kind == "fred_observation"
        for candle in series.candles:
            if any(not _valid(value) or (not is_fred_observation and float(value) <= 0) for value in (candle.close, candle.high, candle.low)):
                return {"symbol": resolved, "error": "invalid_ohlc"}
        idx = [c.timestamp for c in series.candles]
        raw = pd.Series([c.close for c in series.candles], index=idx)
        adjusted_values = [
            c.distribution_adjusted_close if price_mode == "distribution_adjusted" else c.split_adjusted_close
            for c in series.candles
        ]
        # adjusted_close is the legacy normalized provider field. It is used
        # only when the provider has not populated the explicit channels.
        if any(value is None for value in adjusted_values):
            adjusted_values = [c.adjusted_close for c in series.candles]
        has_adjusted = all(value is not None and _valid(value) for value in adjusted_values)
        use_adjusted = price_mode in {"split_adjusted", "distribution_adjusted"} and has_adjusted
        closes = pd.Series([value if use_adjusted else c.close for value, c in zip(adjusted_values, series.candles)], index=idx)
        # OHLC must use the same price basis as close. With only adjusted close
        # available, scale the raw range by the per-candle adjustment factor.
        if is_fred_observation:
            highs, lows = closes.copy(), closes.copy()
        else:
            factors = closes / raw.replace(0, math.nan)
            highs = pd.Series([c.high for c in series.candles], index=idx) * factors
            lows = pd.Series([c.low for c in series.candles], index=idx) * factors
        if timeframe == "weekly":
            closes = closes.resample("W-FRI").last().dropna()
            highs = highs.resample("W-FRI").max().reindex(closes.index)
            lows = lows.resample("W-FRI").min().reindex(closes.index)
            raw = raw.resample("W-FRI").last().reindex(closes.index)
        rv, rp = _last_two(rsi(closes, 14)); md, mp = _last_two(macd(closes, 12, 26, 9)["histogram"]); mdf = macd(closes, 12, 26, 9)
        mas = {f"sma{x}": sma(closes, x) for x in (20, 50, 100, 200)}
        av = atr(highs, lows, closes, 14)
        volatility = _annualized_volatility(closes, is_fred_observation)
        drawdown = closes.iloc[-1] / closes.cummax().iloc[-1] - 1 if not closes.empty else None
        persistence = int(sum((closes.tail(5) >= closes.tail(5).rolling(20, min_periods=1).mean()).tolist()))
        ma_values = [float(v.iloc[-1]) if not v.empty else None for v in mas.values()]
        slopes_up = all(
            len(v.dropna()) > 4 and float(v.iloc[-1]) > float(v.iloc[-5]) for v in mas.values()
        )
        aligned = _alignment(ma_values, True)
        if timeframe == "weekly":
            above_sma50 = closes >= mas["sma50"]
            persistence_pct = float(above_sma50.tail(52).mean()) if not above_sma50.tail(52).empty else 0.0
            regime_score = (30 if aligned else 0) + (25 if slopes_up else 0) + (20 if persistence_pct >= .70 else round(20 * persistence_pct / .70))
            regime_score += 15 if rv is not None and rv >= 50 else 0
            regime_score += 10 if drawdown is not None and drawdown > -.25 else 0
        else:
            persistence_pct = None
            regime_score = None
        metrics = {"drawdown_pct": float(drawdown) if drawdown is not None else None, "volatility_pct": volatility, "trend_persistence_days": persistence, "timeframe": timeframe, "trend_regime_score": regime_score, "weekly_persistence_pct": persistence_pct, "weekly_ma_slopes_up": slopes_up if timeframe == "weekly" else None}
        return {"symbol": resolved, "currency": series.currency, "provider": series.provider, "series_kind": series.series_kind, "as_of": closes.index[-1].isoformat(), "price": float(closes.iloc[-1]), "raw_price": float(raw.iloc[-1]), "adjustment_data_available": has_adjusted, "resolved_price_mode": price_mode if use_adjusted else "raw", "metrics": metrics, "used_equivalent": resolution.used_equivalent, "resolution_method": resolution.resolution_method, "candidates_tried": resolution.candidates_tried, "indicators": {"rsi14": round_value(rv, 2), "rsi14_prev": round_value(rp, 2), "macd": round_value(_last_two(mdf["macd"])[0], 4), "macd_signal": round_value(_last_two(mdf["signal"])[0], 4), "macd_histogram": round_value(md, 4), "macd_histogram_prev": round_value(mp, 4), **{k: round_value(float(v.iloc[-1]) if not v.empty else None, 4) for k, v in mas.items()}, "atr14": round_value(float(av.iloc[-1]) if not av.empty else None, 4)}}

    def _resolve_config(self, profile: str, horizon: str) -> tuple[str, str, dict[str, Any]]:
        if profile in _LEGACY:
            profile, horizon = _LEGACY[profile]
        if profile == "auto":
            profile = "trend_weekly_etf"
        if profile not in PROFILE_CONFIG:
            raise ValueError(f"unknown evaluation profile: {profile}")
        if horizon not in HORIZON_CONFIG:
            raise ValueError(f"unknown signal horizon: {horizon}")
        config = {**PROFILE_CONFIG[profile], **HORIZON_CONFIG[horizon], "extension": dict(PROFILE_CONFIG[profile]["extension"]), "weights": dict(PROFILE_CONFIG[profile]["weights"])}
        if "history_period" in PROFILE_CONFIG[profile]:
            config["history_period"] = PROFILE_CONFIG[profile]["history_period"]
        return profile, horizon, config

    def evaluate_signal(self, symbol: str, profile: str = "trend_standard", horizon: SignalHorizon = "medium_term", include_evidence: bool = True) -> SignalEvaluation:
        requested_profile = profile
        profile, horizon, config = self._resolve_config(profile, horizon)
        try:
            snapshot = self.get_snapshot(symbol, config["history_period"], config["price_mode"], config.get("timeframe", "daily"))
        except TypeError:
            # Test doubles and third-party subclasses may still implement the
            # older two-argument snapshot hook.
            snapshot = self.get_snapshot(symbol, config["history_period"])
        if "error" in snapshot:
            return {"symbol": symbol, "profile": requested_profile, "horizon": horizon, "error": snapshot["error"]}  # type: ignore[return-value]
        price = snapshot.get("price")
        if not _valid(price) or float(price) <= 0:
            # Keep the historical error envelope for callers that used the old
            # horizon-as-profile API; successful evaluations use the new profile.
            error_profile = "medium_term" if requested_profile == "trend_standard" and horizon == "medium_term" else requested_profile
            return {"symbol": symbol, "profile": error_profile, "horizon": horizon, "error": "invalid_or_missing_price"}  # type: ignore[return-value]
        i = snapshot.get("indicators", {})
        if not isinstance(i, dict):
            return {"symbol": symbol, "profile": requested_profile, "horizon": horizon, "error": "invalid_indicators"}  # type: ignore[return-value]
        indicator_keys = ["rsi14", "rsi14_prev", "macd", "macd_signal", "macd_histogram", "macd_histogram_prev", "atr14"] + [f"sma{x}" for x in (20, 50, 100, 200)]
        if any(key in i and i[key] is not None and not _valid(i[key]) for key in indicator_keys):
            return {"symbol": symbol, "profile": requested_profile, "horizon": horizon, "error": "invalid_indicators"}  # type: ignore[return-value]
        p = float(price)
        raw_value = snapshot.get("raw_price")
        raw_price = p if raw_value is None else _number(raw_value)
        if raw_price is None or (raw_price <= 0 and snapshot.get("series_kind") != "fred_observation"):
            return {"symbol": symbol, "profile": requested_profile, "horizon": horizon, "error": "invalid_or_missing_raw_price"}  # type: ignore[return-value]
        ma = [_number(i.get(f"sma{x}")) for x in (20, 50, 100, 200)]
        r, rp, mh, mhp, a = _number(i.get("rsi14")), _number(i.get("rsi14_prev")), _number(i.get("macd_histogram")), _number(i.get("macd_histogram_prev")), _number(i.get("atr14"))
        if r is not None and not 0 <= r <= 100 or rp is not None and not 0 <= rp <= 100:
            return {"symbol": symbol, "profile": requested_profile, "horizon": horizon, "error": "invalid_rsi"}  # type: ignore[return-value]
        if a is not None and a < 0:
            return {"symbol": symbol, "profile": requested_profile, "horizon": horizon, "error": "invalid_atr"}  # type: ignore[return-value]
        supplied = snapshot.get("metrics", {})
        if not isinstance(supplied, dict):
            return {"symbol": symbol, "profile": requested_profile, "horizon": horizon, "error": "invalid_metrics"}  # type: ignore[return-value]
        if any(value is not None and not _valid(value) for value in supplied.values() if isinstance(value, (int, float))):
            return {"symbol": symbol, "profile": requested_profile, "horizon": horizon, "error": "invalid_metrics"}  # type: ignore[return-value]
        drawdown = _number(supplied.get("drawdown_pct")); volatility = _number(supplied.get("volatility_pct")); regime_score = _number(supplied.get("trend_regime_score"))
        if drawdown is None: drawdown = _number(supplied.get("drawdown"))
        bullish = _alignment(ma, True); bearish = _alignment(ma, False); primary = ma[2] if horizon == "short_term" else ma[3]
        trend_up = primary is not None and p >= primary and (ma[1] is None or ma[2] is None or ma[1] >= ma[2])
        if config["use_ma_alignment"]:
            trend_up = trend_up and bullish
        if profile == "trend_weekly_etf":
            trend_up = trend_up and bool(supplied.get("weekly_ma_slopes_up")) and regime_score is not None and regime_score >= config["minimum_regime_score"]
        distance = (p - (ma[1] or p)) / a if a and a > 0 else 0.0
        extended = bool(config["extension"]["enabled"] and ((config["extension"]["method"] == "atr" and distance > (2.5 if horizon == "short_term" else 3.0)) or (config["extension"]["method"] == "zscore" and _number(supplied.get("distance_zscore")) is not None and float(supplied["distance_zscore"]) > 2.0)))
        weakening = (mh is not None and mhp is not None and mh < mhp) or (r is not None and rp is not None and rp >= 70 > r) or (ma[0] is not None and p < ma[0])
        low_vol = profile.startswith("low_volatility_")
        if profile == "mean_reversion":
            zscore = _number(supplied.get("distance_zscore"))
            if zscore is not None and zscore <= -2 and (r is None or r < 45):
                state = "BULLISH_PULLBACK"
            elif zscore is not None and zscore >= 2 and (r is None or r > 55):
                state = "BULLISH_EXTENDED_WEAKENING" if weakening else "BULLISH_EXTENDED"
            else:
                state = "NEUTRAL"
        elif low_vol:
            if profile == "low_volatility_distribution" and not bool(snapshot.get("adjustment_data_available", False)):
                # Do not turn an unclassified cash-flow gap into a technical loss.
                state = "NEUTRAL"
                drawdown = None
            else:
                severe = drawdown is not None and drawdown < -0.08
                state = "STRONG_BEARISH" if severe and bearish else "BEARISH" if severe or not trend_up else "BULLISH"
        elif profile == "trend_weekly_etf" and not trend_up:
            state = "NEUTRAL"
        elif bullish and (not config["use_macd"] or mh is None or mh > 0) and not extended:
            rsi_max = config.get("rsi_entry_max", 70)
            rsi_confirmed = not config["use_rsi"] or (r is not None and (r <= rsi_max if profile == "trend_weekly_etf" else 45 <= r <= rsi_max))
            state = "STRONG_BULLISH" if rsi_confirmed else "BULLISH"
        elif extended and weakening: state = "BULLISH_EXTENDED_WEAKENING"
        elif extended: state = "BULLISH_EXTENDED"
        elif trend_up and ma[0] is not None and p <= ma[0] and (r is None or r < 55): state = "BULLISH_PULLBACK"
        elif bearish and (mh is None or mh < 0): state = "STRONG_BEARISH"
        elif not trend_up and mh is not None and mh > 0: state = "BEARISH_REVERSAL_ATTEMPT"
        else: state = "NEUTRAL"
        persistence = _number(supplied.get("trend_persistence_days"))
        if persistence is not None and persistence < config["confirmation_days"]:
            if state == "STRONG_BULLISH":
                state = "BULLISH"
            elif state == "STRONG_BEARISH":
                state = "BEARISH"
        entry, position = PROFILE_SIGNAL_OVERRIDES.get(profile, {}).get(state, STATE_SIGNAL_MAP[state])
        enabled = [ma[0], ma[1], ma[2], ma[3]] + ([r] if config["use_rsi"] else []) + ([mh] if config["use_macd"] else []) + ([a] if config["use_atr"] else [])
        coverage = sum(v is not None for v in enabled) / len(enabled) if enabled else 1.0
        weights = config["weights"]
        components = {"trend": round((12 if trend_up else -12) * weights.get("trend", 0) / .4), "momentum": round((8 if mh is not None and mh > 0 else -8) * weights.get("momentum", 0) / .3) if config["use_macd"] else 0, "extension": round(-8 * weights.get("extension", 0) / .2) if extended else 0, "stability": round((8 if volatility is None or volatility < 2 else -8) * weights.get("stability", 0) / .4) if low_vol else 0, "drawdown": round((8 if drawdown is not None and drawdown > -0.08 else -8) * weights.get("drawdown", 0) / .3) if drawdown is not None else 0}
        score = max(-100, min(100, sum(components.values())))
        warnings: list[str] = []; adjustment = config["price_mode"] == "distribution_adjusted"; available = bool(snapshot.get("adjustment_data_available", False))
        resolved_mode = snapshot.get("resolved_price_mode", config["price_mode"] if available else "raw")
        if adjustment and not available:
            resolved_mode, warnings = "split_adjusted", ["Distribution-adjusted price series unavailable", "Raw distribution gaps may affect technical indicators"]
        confidence: Literal["low", "medium", "high"] = "low" if coverage < .5 or (adjustment and not available) else "high" if coverage >= .8 and not warnings else "medium"
        levels = {} if low_vol else self._levels(ma, p)
        metrics = {"raw_price": raw_price, "analysis_price": p, "primary_trend": "bullish" if trend_up else "bearish", "volatility_regime": "low" if volatility is not None and volatility < 2 else "normal", "drawdown_pct": drawdown, "extended": extended, "weakening": weakening, "trend_regime_score": regime_score, "timeframe": supplied.get("timeframe", "daily")}
        reasons = ["stable_adjusted_return" if low_vol and trend_up else "price_above_primary_average" if trend_up else "price_below_primary_average"]
        if low_vol and drawdown is not None and drawdown > -0.08: reasons.append("drawdown_within_expected_range")
        result: SignalEvaluation = {"symbol": snapshot.get("symbol", symbol), "provider": snapshot.get("provider", "yahoo"), "series_kind": snapshot.get("series_kind", "price"), "profile": requested_profile, "horizon": horizon, "technical_state": state, "entry_signal": entry, "position_signal": position, "score": int(score), "confidence": confidence, "indicator_coverage": round(coverage, 2), "requested_price_mode": config["price_mode"], "resolved_price_mode": resolved_mode, "adjustment_data_available": bool(available), "metrics": metrics, "technical_metrics": metrics, "score_components": components, "levels": levels, "warnings": warnings, "reasons": reasons}
        if include_evidence:
            result["resolved_configuration"] = {"price_mode": config["price_mode"], "timeframe": config.get("timeframe", "daily"), "confirmation_days": config["confirmation_days"], "use_rsi": config["use_rsi"], "use_macd": config["use_macd"], "extension_enabled": config["extension"]["enabled"], "use_ma_alignment": config["use_ma_alignment"], "minimum_regime_score": config.get("minimum_regime_score"), "rsi_entry_max": config.get("rsi_entry_max"), "weights": dict(config["weights"])}
        return result

    @staticmethod
    def _levels(ma: list[Optional[float]], price: float) -> dict:
        supports = sorted((v for v in ma if v is not None and v < price), reverse=True); resistances = sorted(v for v in ma if v is not None and v > price)
        result = {"supports": supports, "resistances": resistances}
        if supports: result.update({"support_1": round_value(supports[0], 2)})
        if len(supports) > 1: result.update({"support_2": round_value(supports[1], 2)})
        if resistances: result.update({"resistance_1": round_value(resistances[0], 2)})
        return result

    def compare_snapshots(self, symbols: List[str], profile: str = "trend_standard", horizon: SignalHorizon = "medium_term") -> List[SignalEvaluation]:
        return [self.evaluate_signal(sym, profile, horizon, True) for sym in symbols]
