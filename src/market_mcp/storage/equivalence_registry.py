"""Persistencia de equivalencias de símbolos Yahoo, copiado/adaptado de scripts/, sin dependencias externas."""

from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple


def utc_now_iso() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def _safe_str(value: Any) -> str:
    if value is None:
        return ""
    return str(value).strip()


def _parse_timestamp(value: Any) -> Tuple[int, str]:
    text = _safe_str(value)
    if not text:
        return (0, "")
    try:
        normalized = text.replace("Z", "+00:00")
        ts = datetime.fromisoformat(normalized)
        if ts.tzinfo is None:
            ts = ts.replace(tzinfo=timezone.utc)
        return (int(ts.timestamp()), text)
    except Exception:
        return (0, text)


def load_flat_mapping(path: Optional[Path]) -> Dict[str, str]:
    if path is None or not path.exists():
        return {}
    with path.open("r", encoding="utf-8") as f:
        data = json.load(f)
    if not isinstance(data, dict):
        raise ValueError("Ticker memory file must be a JSON object")
    if "entries" in data or "records" in data:
        return project_registry_mapping(data)
    return {str(k): _safe_str(v) for k, v in data.items()}


def project_registry_mapping(payload: Any) -> Dict[str, str]:
    if isinstance(payload, dict) and "entries" not in payload and "records" not in payload:
        return {str(k): _safe_str(v) for k, v in payload.items()}

    if isinstance(payload, dict):
        entries = payload.get("entries") or payload.get("records") or []
    elif isinstance(payload, list):
        entries = payload
    else:
        return {}

    indexed_entries: List[Tuple[int, int, str, Dict[str, Any]]] = []
    for index, entry in enumerate(entries):
        if not isinstance(entry, dict):
            continue
        status = _safe_str(entry.get("status")).lower()
        if status in {"inactive", "rejected", "ignored", "disabled"}:
            continue
        original = _safe_str(
            entry.get("original_ticker")
            or entry.get("original")
            or entry.get("ticker")
        )
        selected = _safe_str(
            entry.get("selected_yahoo_ticker")
            or entry.get("selected")
            or entry.get("yahoo_ticker")
            or entry.get("resolved_ticker")
        )
        if not original or not selected:
            continue
        updated = _parse_timestamp(entry.get("updated_at_utc") or entry.get("created_at_utc"))
        indexed_entries.append((updated[0], index, original, {"selected": selected}))

    indexed_entries.sort(key=lambda item: (item[0], item[1]))
    mapping: Dict[str, str] = {}
    for _, _, original, payload_entry in indexed_entries:
        mapping[original] = payload_entry["selected"]
    return mapping


def load_registry_payload(path: Optional[Path]) -> Dict[str, Any]:
    if path is None or not path.exists():
        return {"meta": {}, "entries": []}

    with path.open("r", encoding="utf-8") as f:
        data = json.load(f)

    if isinstance(data, list):
        return {"meta": {}, "entries": [entry for entry in data if isinstance(entry, dict)]}

    if isinstance(data, dict):
        if "entries" in data or "records" in data:
            entries = data.get("entries") or data.get("records") or []
            return {
                "meta": dict(data.get("meta") or {}),
                "entries": [entry for entry in entries if isinstance(entry, dict)],
            }
        if all(isinstance(v, str) for v in data.values()):
            timestamp = utc_now_iso()
            return {
                "meta": {
                    "format": "flat_mapping_compat",
                    "updated_at_utc": timestamp,
                },
                "entries": [
                    {
                        "original_ticker": str(k),
                        "selected_yahoo_ticker": _safe_str(v),
                        "status": "accepted",
                        "created_at_utc": timestamp,
                        "updated_at_utc": timestamp,
                    }
                    for k, v in data.items()
                ],
            }

    raise ValueError("Unsupported ticker equivalence registry structure")


def save_registry_payload(path: Path, payload: Dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        json.dumps(payload, ensure_ascii=False, indent=2, sort_keys=False) + "\n",
        encoding="utf-8",
    )


def build_registry_entry(
    *,
    original_ticker: str,
    selected_yahoo_ticker: str,
    source: str,
    source_symbol: Optional[str] = None,
    asset_id: Optional[str] = None,
    name: Optional[str] = None,
    isin: Optional[str] = None,
    reason: Optional[str] = None,
    notes: Optional[str] = None,
    status: str = "accepted",
    created_at_utc: Optional[str] = None,
    updated_at_utc: Optional[str] = None,
) -> Dict[str, Any]:
    now = utc_now_iso()
    created = created_at_utc or now
    updated = updated_at_utc or now
    entry: Dict[str, Any] = {
        "decision_id": f"{original_ticker}->{selected_yahoo_ticker}",
        "original_ticker": original_ticker,
        "selected_yahoo_ticker": selected_yahoo_ticker,
        "source": source,
        "status": status,
        "created_at_utc": created,
        "updated_at_utc": updated,
    }
    optional_fields = {
        "source_symbol": source_symbol,
        "asset_id": asset_id,
        "name": name,
        "isin": isin,
        "reason": reason,
        "notes": notes,
    }
    for key, value in optional_fields.items():
        if _safe_str(value):
            entry[key] = _safe_str(value)
    return entry


def upsert_registry_entry(
    payload: Dict[str, Any],
    entry: Dict[str, Any],
) -> Tuple[bool, Dict[str, Any]]:
    entries = payload.setdefault("entries", [])
    if not isinstance(entries, list):
        raise ValueError("Registry payload entries must be a list")

    unique_key = (
        _safe_str(entry.get("original_ticker")),
        _safe_str(entry.get("selected_yahoo_ticker")),
        _safe_str(entry.get("source")),
        _safe_str(entry.get("source_symbol")),
    )

    for index, existing in enumerate(entries):
        if not isinstance(existing, dict):
            continue
        existing_key = (
            _safe_str(existing.get("original_ticker")),
            _safe_str(existing.get("selected_yahoo_ticker")),
            _safe_str(existing.get("source")),
            _safe_str(existing.get("source_symbol")),
        )
        if existing_key == unique_key:
            merged = dict(existing)
            for key, value in entry.items():
                if _safe_str(value):
                    merged[key] = value
            merged["updated_at_utc"] = entry.get("updated_at_utc") or utc_now_iso()
            if not merged.get("created_at_utc"):
                merged["created_at_utc"] = entry.get("created_at_utc") or merged["updated_at_utc"]
            entries[index] = merged
            payload.setdefault("meta", {})
            payload["meta"]["updated_at_utc"] = merged["updated_at_utc"]
            payload["meta"]["entry_count"] = len(entries)
            return False, merged

    entries.append(dict(entry))
    payload.setdefault("meta", {})
    payload["meta"]["updated_at_utc"] = entry.get("updated_at_utc") or utc_now_iso()
    payload["meta"]["entry_count"] = len(entries)
    return True, entry


class TickerMemoryMap:
    def __init__(self, path: Path) -> None:
        self.path = path
        self._mapping = load_flat_mapping(path)

    def get(self, ticker: str) -> Optional[str]:
        return self._mapping.get(ticker.upper())

    def set(self, ticker: str, yahoo_ticker: str) -> None:
        self._mapping[ticker.upper()] = yahoo_ticker
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self.path.write_text(
            json.dumps(dict(sorted(self._mapping.items())), ensure_ascii=False, indent=2) + "\n",
            encoding="utf-8",
        )

    def as_dict(self) -> Dict[str, str]:
        return dict(self._mapping)


class EquivalenceRegistry:
    def __init__(self, registry_path: Path, memory_map_path: Optional[Path] = None) -> None:
        self.registry_path = registry_path
        self.memory_map_path = memory_map_path
        self._memory = TickerMemoryMap(memory_map_path) if memory_map_path else None

    def lookup(self, original_ticker: str) -> Optional[str]:
        return self._memory.get(original_ticker) if self._memory else None

    def register(
        self,
        original_ticker: str,
        selected_yahoo_ticker: str,
        source: str,
        source_symbol: Optional[str] = None,
        reason: Optional[str] = None,
        notes: Optional[str] = None,
    ) -> Dict[str, Any]:
        registry = load_registry_payload(self.registry_path)
        timestamp = utc_now_iso()
        entry = build_registry_entry(
            original_ticker=original_ticker,
            selected_yahoo_ticker=selected_yahoo_ticker,
            source=source,
            source_symbol=source_symbol,
            reason=reason,
            notes=notes,
            status="accepted",
            created_at_utc=timestamp,
            updated_at_utc=timestamp,
        )
        created, stored_entry = upsert_registry_entry(registry, entry)
        save_registry_payload(self.registry_path, registry)

        memory_updated = False
        if self._memory is not None:
            if self._memory.get(original_ticker) != selected_yahoo_ticker:
                self._memory.set(original_ticker, selected_yahoo_ticker)
                memory_updated = True

        return {
            "created": created,
            "registry_path": str(self.registry_path),
            "memory_map_path": str(self.memory_map_path) if self.memory_map_path else None,
            "entry": stored_entry,
            "registry_entry_count": len(registry.get("entries") or []),
            "memory_updated": memory_updated,
        }

    def list_entries(
        self,
        limit: int = 50,
        status_filter: Optional[str] = None,
    ) -> List[Dict[str, Any]]:
        registry = load_registry_payload(self.registry_path)
        entries = registry.get("entries") or []
        if status_filter:
            entries = [
                e for e in entries
                if _safe_str(e.get("status")).lower() == status_filter.lower()
            ]
        return entries[-limit:]
