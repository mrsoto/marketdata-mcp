"""Tools MCP para tránsito marítimo en chokepoints."""

from __future__ import annotations

from typing import Literal

from market_mcp.services.maritime_chokepoints import MaritimeChokepointService


def get_maritime_chokepoint_status(
    service: MaritimeChokepointService,
    chokepoint: Literal["hormuz", "bab_el_mandeb", "both"] = "both",
    include_history: bool = True,
) -> dict:
    """Obtiene tránsito AIS observado para Ormuz y/o Bab el-Mandeb."""
    reports = service.get_status(chokepoint=chokepoint, include_history=include_history)
    return {"count": len(reports), "source": "IMF PortWatch / UN Global Platform", "reports": [report.model_dump(mode="json") for report in reports]}
