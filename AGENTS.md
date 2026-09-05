# AGENTS.md

Local MCP (stdio) for technical analysis of ETFs/indices/equities with Yahoo equivalents fallback.

## Quick start

```bash
uv sync
uv run market-mcp          # run the MCP server via stdio
```

## Tests

```bash
./.venv/bin/pytest tests/ -v
```

- 28 tests in 3 files: `test_indicators.py`, `test_symbol_resolution.py`, `test_equivalence_registry.py`
- Python 3.14 in the local `.venv` (do not use the `.venv` from the other workspace)
- Shell `VIRTUAL_ENV` points to another project; ignore and use the local `.venv` directly

## Architecture

```
src/market_mcp/
├── server.py                    # FastMCP, 10 tools, stdio entrypoint
├── domain/
│   ├── models.py                # Candle, PriceSeries, IndicatorSnapshot, SymbolResolution, ETFPriceSnapshotReport
│   └── indicators.py           # rsi, macd, sma, atr (custom calculations with pandas, no TA-Lib)
├── providers/
│   ├── base.py                  # Protocol HistoricalPriceProvider
│   ├── yahoo.py                 # YahooProvider (yfinance, symbol normalization)
│   └── symbol_resolution.py     # EXCHANGE_SUFFIX_MAP, UCITS fallbacks, SymbolResolver
├── services/
│   ├── price_snapshot.py        # current/last_week/last_month with equivalents fallback
│   └── technical_analysis.py    # snapshot, signal (3 profiles), compare
├── storage/
│   ├── equivalence_registry.py  # equivalences persistence (JSON, isolated from scripts/)
│   └── cache.py                 # PriceCache + SnapshotCache (diskcache)
└── tools/
    ├── symbols.py               # register/list/get equivalence
    ├── prices.py                # snapshot, history, technical, signal, compare
    └── bootstrap.py             # import from the external OHLCV cache
```

## Key conventions

- **No dependencies on `scripts/`**: the logic for `EXCHANGE_SUFFIX_MAP`, `UCITS_SUFFIX_FALLBACKS` and the equivalences registry was copied/adapted to the MCP package. Do not import from the external scripts workspace.
- **Indicators**: custom calculations with pandas/numpy, no TA-Lib. See `domain/indicators.py`.
- **Domain**: all models use Pydantic v2. `Candle`, `PriceSeries`, `IndicatorSnapshot` are the normalized interface.
- **Abstract provider**: `HistoricalPriceProvider` is a Protocol. Yahoo is the current implementation; the design allows swapping to Polygon/TwelveData/etc.
- **Cache**: `diskcache` with hashed keys by `symbol:interval:period:adjusted`. TTL 6h for OHLCV, 1h for snapshots.
- **Timezone**: all dates are handled in UTC. Use `astimezone(timezone.utc)`, never `replace(tzinfo=...)`.
- **FRED**: `CompositeProvider` routes `T10YIE`, `DFII10`, `DGS10`, `DGS2`, `T10Y2Y` and `DTWEXBGS` to FRED. The explicit `FRED:<id>` prefix is also supported.

## MCP Tools (11)

| Tool | Purpose |
|------|---------|
| `register_ticker_equivalence` | Register persistent equivalence |
| `list_ticker_equivalences` | List equivalences |
| `get_ticker_equivalence` | Query equivalence |
| `get_etf_price_snapshot` | Snapshot with current/last_week/last_month |
| `get_multiple_etf_price_snapshots` | Multiple ETFs |
| `get_price_history` | Candle history |
| `get_technical_snapshot` | Full technical snapshot |
| `evaluate_technical_signal` | Scoring BUY/WAIT/HOLD/REDUCE/SELL |
| `compare_technical_snapshots` | Multi-symbol comparison |
| `get_maritime_chokepoint_status` | AIS transit for Hormuz and Bab el-Mandeb |
| `bootstrap_cache_from_external` | Import OHLCV from external parquet |

## Data paths

Runtime data is owned by the shared `market-data` package and must be outside
the repository. Set `MARKET_DATA_ROOT`, for example:

```bash
export MARKET_DATA_ROOT="$HOME/ai/var/market-data"
```

The core derives equivalence, OHLCV and snapshot paths from that root.

## Client configuration

### OpenCode (`opencode.json`)

```json
{
  "mcpServers": {
    "market-analysis": {
      "type": "local",
      "command": ["uv", "--directory", ".../mcp/marketdata", "run", "market-mcp"],
      "enabled": true
    }
  }
}
```

### Codex (standard format)

```json
{
  "mcpServers": {
    "market-analysis": {
      "command": "uv",
      "args": ["--directory", ".../mcp/marketdata", "run", "market-mcp"]
    }
  }
}
```
