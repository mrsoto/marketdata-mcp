"""Cliente pequeño para los datos diarios de chokepoints de IMF PortWatch."""

from __future__ import annotations

import json
from typing import Any, Dict, List
from urllib.parse import urlencode
from urllib.request import Request, urlopen


class PortWatchProvider:
    endpoint = (
        "https://services9.arcgis.com/weJ1QsnbMYJlCHdG/arcgis/rest/services/"
        "Daily_Chokepoints_Data/FeatureServer/0/query"
    )

    def get_daily_observations(self, port_id: str, limit: int = 400) -> List[Dict[str, Any]]:
        params = {
            "where": f"portid = '{port_id}'",
            "outFields": "date,portid,portname,n_total,n_tanker,capacity,capacity_tanker",
            "returnGeometry": "false",
            "orderByFields": "date DESC",
            "resultRecordCount": str(limit),
            "f": "json",
        }
        request = Request(f"{self.endpoint}?{urlencode(params)}", headers={"User-Agent": "market-mcp/0.1"})
        with urlopen(request, timeout=20) as response:
            payload = json.load(response)
        if "error" in payload:
            raise RuntimeError(payload["error"].get("message", "PortWatch query failed"))
        return [feature["attributes"] for feature in payload.get("features", [])]
