# market-mcp

Local MCP (stdio) for technical analysis of ETFs / indices / equities.

Features:
- Symbol resolution with equivalents fallback (exchange suffixes + UCITS).
- Automatic FRED routing for macroeconomic series alongside Yahoo Finance.
- Local equivalences persistence with registration and query tools.
- Locally calculated indicators (RSI, MACD, SMAs).
- Snapshots at three dates: `current`, `last_week`, `last_month`.
- Disk cache for OHLCV and snapshots.
- Compact responses with explicit reporting of when an equivalent was used.

## Installation

```bash
uv sync
```

## Execution

```bash
uv run market-mcp
```

## Configuration in Codex / OpenCode

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

### Codex

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

## Exposed tools

- `register_ticker_equivalence`
- `list_ticker_equivalences`
- `get_ticker_equivalence`
- `get_etf_price_snapshot`
- `get_multiple_etf_price_snapshots`
- `get_price_history`
- `get_technical_snapshot`
- `evaluate_technical_signal`
- `compare_technical_snapshots`
- `get_maritime_chokepoint_status`

## Maritime chokepoints

`get_maritime_chokepoint_status` consults daily AIS observations from IMF
PortWatch for `hormuz`, `bab_el_mandeb`, or `both`. It reports vessel counts,
tankers, estimated capacity, rolling averages, data freshness, and AIS caveats.
It does not provide maritime insurance premiums or coverage decisions.

## FRED series

The following identifiers are routed automatically to FRED's CSV endpoint:

- `T10YIE` - 10-Year Breakeven Inflation Rate
- `DFII10` - 10-Year Treasury Inflation-Indexed Security
- `DGS10` - 10-Year Treasury Constant Maturity Rate
- `DGS2` - 2-Year Treasury Constant Maturity Rate
- `T10Y2Y` - 10-Year Treasury Constant Maturity Minus 2-Year Treasury Constant Maturity
- `DTWEXBGS` - Nominal Broad U.S. Dollar Index

The explicit `FRED:<id>` form is also supported. FRED observations are scalar
daily values normalized as candles with equal open/high/low/close fields and
no volume. Negative values, such as an inverted yield spread, are supported.

## Persistent data

By default, relative paths are used:

- `data/yahoo_ticker_equivalence_registry.json`
- `data/yahoo_ticker_memory.json`
- `data/ohlcv_cache/`
- `data/snapshot_cache/`

Can be overridden with environment variables:

- `MARKET_MCP_EQUIVALENCE_REGISTRY_PATH`
- `MARKET_MCP_TICKER_MEMORY_PATH`
- `MARKET_MCP_OHLCV_CACHE_DIR`
- `MARKET_MCP_SNAPSHOT_CACHE_DIR`
