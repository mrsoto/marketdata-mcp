"""Consulta y normalización de tránsito AIS en chokepoints marítimos."""

from __future__ import annotations

from datetime import date, datetime, timezone
from typing import Dict, Literal, Optional

from market_mcp.domain.models import MaritimeChokepointReport, MaritimeObservation
from market_mcp.providers.portwatch import PortWatchProvider

Chokepoint = Literal["hormuz", "bab_el_mandeb", "both"]
CHOKEPOINTS = {
    "hormuz": ("Strait of Hormuz", "chokepoint6"),
    "bab_el_mandeb": ("Bab el-Mandeb Strait", "chokepoint4"),
}
WARNING = "AIS data may be incomplete, spoofed or delayed"


class MaritimeChokepointService:
    def __init__(self, provider: Optional[PortWatchProvider] = None) -> None:
        self.provider = provider or PortWatchProvider()

    def get_status(self, chokepoint: Chokepoint = "both", include_history: bool = True) -> list[MaritimeChokepointReport]:
        names = list(CHOKEPOINTS) if chokepoint == "both" else [chokepoint]
        return [self._report(name, include_history) for name in names]

    def _report(self, key: str, include_history: bool) -> MaritimeChokepointReport:
        name, port_id = CHOKEPOINTS[key]
        try:
            rows = self.provider.get_daily_observations(port_id)
        except Exception as exc:
            return MaritimeChokepointReport(
                name=name, port_id=port_id, status="NO_DATA", warnings=[f"PortWatch query failed: {exc}"]
            )
        observations = [self._observation(row) for row in rows if row.get("date")]
        observations.sort(key=lambda item: item.date, reverse=True)
        if not observations:
            return MaritimeChokepointReport(name=name, port_id=port_id, status="NO_DATA", warnings=[WARNING])

        latest = observations[0]
        freshness = max(0, (datetime.now(timezone.utc).date() - date.fromisoformat(latest.date)).days)
        windows = {
            "last_7_days": observations[:7],
            "last_30_days": observations[:30],
            "last_365_days": observations[:365],
        }
        averages = {window: self._averages(values) for window, values in windows.items()}
        average_30 = averages["last_30_days"]["total_vessels"]
        change = self._change(latest.total_vessels, average_30)
        return MaritimeChokepointReport(
            name=name,
            port_id=port_id,
            latest_date=latest.date,
            freshness_days=freshness,
            status="STALE" if freshness > 10 else "DATA_AVAILABLE",
            latest=latest,
            averages=averages,
            latest_vs_30d_average_pct=change,
            history=observations if include_history else [],
            warnings=[WARNING],
        )

    @staticmethod
    def _observation(row: Dict[str, object]) -> MaritimeObservation:
        def integer(name: str) -> int:
            return int(row.get(name) or 0)

        return MaritimeObservation(
            date=str(row["date"]),
            total_vessels=integer("n_total"),
            tankers=integer("n_tanker"),
            estimated_capacity=integer("capacity"),
            estimated_tanker_capacity=integer("capacity_tanker"),
        )

    @staticmethod
    def _averages(values: list[MaritimeObservation]) -> Dict[str, Optional[float]]:
        if not values:
            return {"total_vessels": None, "tankers": None, "estimated_capacity": None, "estimated_tanker_capacity": None}
        count = len(values)
        return {
            "total_vessels": round(sum(item.total_vessels for item in values) / count, 2),
            "tankers": round(sum(item.tankers for item in values) / count, 2),
            "estimated_capacity": round(sum(item.estimated_capacity for item in values) / count, 2),
            "estimated_tanker_capacity": round(sum(item.estimated_tanker_capacity for item in values) / count, 2),
        }

    @staticmethod
    def _change(value: int, average: Optional[float]) -> Optional[float]:
        if not average:
            return None
        return round((value / average - 1) * 100, 2)
