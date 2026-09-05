"""Tests para equivalence registry."""

from __future__ import annotations

import json
import tempfile
from pathlib import Path

from market_data.storage.equivalence_registry import (
    EquivalenceRegistry,
    TickerMemoryMap,
    build_registry_entry,
    load_flat_mapping,
    load_registry_payload,
    upsert_registry_entry,
)


class TestFlatMapping:
    def test_load_flat(self, tmp_path: Path):
        path = tmp_path / "memory.json"
        path.write_text(json.dumps({"CSKR": "CSKR.L", "JPGL": "JPGL.L"}))
        mapping = load_flat_mapping(path)
        assert mapping["CSKR"] == "CSKR.L"
        assert mapping["JPGL"] == "JPGL.L"

    def test_load_empty(self, tmp_path: Path):
        path = tmp_path / "missing.json"
        mapping = load_flat_mapping(path)
        assert mapping == {}


class TestRegistryPayload:
    def test_load_empty(self, tmp_path: Path):
        path = tmp_path / "registry.json"
        payload = load_registry_payload(path)
        assert payload["entries"] == []

    def test_upsert_creates(self, tmp_path: Path):
        payload = {"entries": []}
        entry = build_registry_entry(
            original_ticker="CSKR",
            selected_yahoo_ticker="CSKR.L",
            source="test",
        )
        created, stored = upsert_registry_entry(payload, entry)
        assert created is True
        assert stored["original_ticker"] == "CSKR"
        assert len(payload["entries"]) == 1

    def test_upsert_updates_same_selected(self, tmp_path: Path):
        payload = {"entries": []}
        entry1 = build_registry_entry(
            original_ticker="CSKR",
            selected_yahoo_ticker="CSKR.L",
            source="test",
        )
        upsert_registry_entry(payload, entry1)
        entry2 = build_registry_entry(
            original_ticker="CSKR",
            selected_yahoo_ticker="CSKR.L",
            source="test",
            notes="updated",
        )
        created, stored = upsert_registry_entry(payload, entry2)
        assert created is False
        assert stored["notes"] == "updated"
        assert len(payload["entries"]) == 1

    def test_upsert_different_selected_creates_new(self, tmp_path: Path):
        payload = {"entries": []}
        entry1 = build_registry_entry(
            original_ticker="CSKR",
            selected_yahoo_ticker="CSKR.L",
            source="test",
        )
        upsert_registry_entry(payload, entry1)
        entry2 = build_registry_entry(
            original_ticker="CSKR",
            selected_yahoo_ticker="CSKR.DE",
            source="test",
        )
        created, stored = upsert_registry_entry(payload, entry2)
        assert created is True
        assert len(payload["entries"]) == 2


class TestTickerMemoryMap:
    def test_set_and_get(self, tmp_path: Path):
        path = tmp_path / "memory.json"
        mem = TickerMemoryMap(path)
        mem.set("CSKR", "CSKR.L")
        assert mem.get("CSKR") == "CSKR.L"
        assert mem.get("cskr") == "CSKR.L"

    def test_missing(self, tmp_path: Path):
        path = tmp_path / "memory.json"
        mem = TickerMemoryMap(path)
        assert mem.get("NOPE") is None


class TestEquivalenceRegistry:
    def test_register_and_lookup(self, tmp_path: Path):
        reg_path = tmp_path / "registry.json"
        mem_path = tmp_path / "memory.json"
        reg = EquivalenceRegistry(reg_path, mem_path)

        result = reg.register(
            original_ticker="JPGL:GB",
            selected_yahoo_ticker="JPGL.L",
            source="test",
            reason="Unit test",
        )
        assert result["created"] is True
        assert result["memory_updated"] is True

        resolved = reg.lookup("JPGL:GB")
        assert resolved == "JPGL.L"

    def test_list_entries(self, tmp_path: Path):
        reg_path = tmp_path / "registry.json"
        reg = EquivalenceRegistry(reg_path)
        reg.register("A", "A.L", "test")
        reg.register("B", "B.DE", "test")
        entries = reg.list_entries()
        assert len(entries) == 2
