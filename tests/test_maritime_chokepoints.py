"""Tests del estado de tránsito marítimo de PortWatch."""

from __future__ import annotations

from datetime import date, datetime, timedelta, timezone

from market_mcp.services.maritime_chokepoints import MaritimeChokepointService
from market_mcp.tools.maritime import get_maritime_chokepoint_status


class FakePortWatchProvider:
    def __init__(self, rows: list[dict] | None = None, error: Exception | None = None) -> None:
        self.rows = rows or []
        self.error = error

    def get_daily_observations(self, port_id: str, limit: int = 400) -> list[dict]:
        if self.error:
            raise self.error
        return self.rows


def _rows(days: int = 30) -> list[dict]:
    today = datetime.now(timezone.utc).date()
    return [
        {
            "date": (today - timedelta(days=index)).isoformat(),
            "n_total": 10 + index,
            "n_tanker": 2 + index,
            "capacity": 100 + index,
            "capacity_tanker": 50 + index,
        }
        for index in range(days)
    ]


def test_returns_hormuz_status_and_rolling_averages() -> None:
    service = MaritimeChokepointService(FakePortWatchProvider(_rows()))

    report = service.get_status("hormuz", include_history=False)[0]

    assert report.name == "Strait of Hormuz"
    assert report.port_id == "chokepoint6"
    assert report.status == "DATA_AVAILABLE"
    assert report.latest.total_vessels == 10
    assert report.averages["last_7_days"]["total_vessels"] == 13.0
    assert report.history == []
    assert report.latest_vs_30d_average_pct == -59.18


def test_marks_old_portwatch_data_as_stale() -> None:
    old = datetime.now(timezone.utc).date() - timedelta(days=11)
    rows = [{**_rows(1)[0], "date": old.isoformat()}]

    report = MaritimeChokepointService(FakePortWatchProvider(rows)).get_status("bab_el_mandeb")[0]

    assert report.status == "STALE"
    assert report.freshness_days == 11
    assert report.name == "Bab el-Mandeb Strait"


def test_both_returns_two_reports_through_tool() -> None:
    result = get_maritime_chokepoint_status(
        MaritimeChokepointService(FakePortWatchProvider(_rows(2))),
        chokepoint="both",
        include_history=False,
    )

    assert result["count"] == 2
    assert [item["port_id"] for item in result["reports"]] == ["chokepoint6", "chokepoint4"]
    assert "insurance" not in str(result).lower()


def test_source_failure_is_reported_as_no_data() -> None:
    service = MaritimeChokepointService(FakePortWatchProvider(error=RuntimeError("offline")))

    report = service.get_status("hormuz")[0]

    assert report.status == "NO_DATA"
    assert "offline" in report.warnings[0]
