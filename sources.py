from __future__ import annotations
import time
import re
from datetime import datetime, timezone
from typing import Any
import httpx

from .config import settings
from .indicators import atr, rsi, pi_cycle_status

COINGECKO_IDS = {
    "BTC": "bitcoin",
    "XRP": "ripple",
    "ONDO": "ondo-finance",
    "AERO": "aerodrome-finance",
    "CFG": "centrifuge",
}

_cache: dict[str, tuple[float, Any]] = {}

def now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()

async def get_json(url: str, params: dict[str, Any] | None = None, headers: dict[str, str] | None = None, timeout: float = 20.0) -> Any:
    async with httpx.AsyncClient(timeout=timeout, follow_redirects=True) as client:
        r = await client.get(url, params=params, headers=headers)
        r.raise_for_status()
        return r.json()

async def get_text(url: str, timeout: float = 20.0) -> str:
    async with httpx.AsyncClient(timeout=timeout, follow_redirects=True) as client:
        r = await client.get(url)
        r.raise_for_status()
        return r.text

async def cached(key: str, fn, ttl: int | None = None):
    ttl = ttl or settings.cache_ttl_seconds
    ts_val = _cache.get(key)
    if ts_val and time.time() - ts_val[0] < ttl:
        return ts_val[1]
    val = await fn()
    _cache[key] = (time.time(), val)
    return val

def cg_headers() -> dict[str, str]:
    headers = {"accept": "application/json"}
    if settings.coingecko_api_key:
        headers["x-cg-demo-api-key"] = settings.coingecko_api_key
    return headers

async def coingecko_market_data() -> dict[str, Any]:
    ids = ",".join(COINGECKO_IDS.values())
    async def fetch():
        return await get_json(
            "https://api.coingecko.com/api/v3/coins/markets",
            params={
                "vs_currency": "usd",
                "ids": ids,
                "order": "market_cap_desc",
                "per_page": 250,
                "page": 1,
                "sparkline": "false",
                "price_change_percentage": "24h,7d,30d"
            },
            headers=cg_headers()
        )
    rows = await cached("cg_markets", fetch)
    by_id = {r["id"]: r for r in rows}
    out = {}
    for sym, cid in COINGECKO_IDS.items():
        r = by_id.get(cid, {})
        out[sym] = {
            "source": "CoinGecko",
            "price": r.get("current_price"),
            "market_cap": r.get("market_cap"),
            "volume_24h": r.get("total_volume"),
            "price_change_24h_pct": r.get("price_change_percentage_24h"),
            "price_change_7d_pct": r.get("price_change_percentage_7d_in_currency"),
            "price_change_30d_pct": r.get("price_change_percentage_30d_in_currency"),
        }
    return out

async def coingecko_ohlc(symbol: str, days: int = 400) -> list[dict[str, float]]:
    cid = COINGECKO_IDS[symbol]
    async def fetch():
        return await get_json(
            f"https://api.coingecko.com/api/v3/coins/{cid}/ohlc",
            params={"vs_currency": "usd", "days": days},
            headers=cg_headers()
        )
    raw = await cached(f"cg_ohlc_{symbol}_{days}", fetch, ttl=900)
    # CoinGecko OHLC rows: [timestamp, open, high, low, close]
    return [
        {"timestamp": row[0], "open": float(row[1]), "high": float(row[2]), "low": float(row[3]), "close": float(row[4])}
        for row in raw
    ]

async def btc_global_dominance() -> dict[str, Any]:
    async def fetch():
        return await get_json("https://api.coingecko.com/api/v3/global", headers=cg_headers())
    data = await cached("cg_global", fetch, ttl=300)
    pct = data.get("data", {}).get("market_cap_percentage", {}).get("btc")
    return {
        "value": pct,
        "source": "CoinGecko global market_cap_percentage.btc",
        "timestamp": now_iso()
    }

async def fear_greed() -> dict[str, Any]:
    async def fetch():
        return await get_json("https://api.alternative.me/fng/", params={"limit": 1, "format": "json"})
    try:
        data = await cached("fear_greed", fetch, ttl=1800)
        item = data.get("data", [{}])[0]
        return {
            "value": int(item["value"]) if item.get("value") is not None else None,
            "classification": item.get("value_classification"),
            "source": "alternative.me Fear & Greed API",
            "timestamp": now_iso()
        }
    except Exception as e:
        return {"value": None, "classification": None, "source": "alternative.me", "error": str(e), "timestamp": now_iso()}

async def cbbi_score() -> dict[str, Any]:
    # CBBI has a public site and free API according to its own site, but endpoint format can change.
    # This fallback scrapes the public page for confidence percentage. If it fails, return null.
    try:
        html = await cached("cbbi_html", lambda: get_text("https://colintalkscrypto.com/cbbi/"), ttl=7200)
        patterns = [
            r"CONFIDENCE WE ARE AT THE PEAK:\s*</[^>]+>\s*<[^>]+>\s*([0-9]+(?:\.[0-9]+)?)",
            r"confidence[^0-9]{0,80}([0-9]+(?:\.[0-9]+)?)\s*%"
        ]
        for p in patterns:
            m = re.search(p, html, flags=re.IGNORECASE | re.DOTALL)
            if m:
                return {"value": float(m.group(1)), "source": "CBBI.info page scrape", "timestamp": now_iso()}
        return {"value": None, "source": "CBBI.info page scrape", "error": "score_not_found", "timestamp": now_iso()}
    except Exception as e:
        return {"value": None, "source": "CBBI.info", "error": str(e), "timestamp": now_iso()}

async def coinglass_funding(symbol: str) -> dict[str, Any]:
    if not settings.coinglass_api_key:
        return {"value": None, "source": "CoinGlass", "error": "missing_COINGLASS_API_KEY", "timestamp": now_iso()}
    headers = {"accept": "application/json", "CG-API-KEY": settings.coinglass_api_key}
    # Endpoint names can differ by plan/version. This uses v4 documented base. Adjust if your CoinGlass plan returns a different shape.
    try:
        data = await get_json(
            "https://open-api-v4.coinglass.com/api/futures/funding-rate/oi-weight-ohlc-history",
            params={"symbol": symbol, "interval": "1d", "limit": 1},
            headers=headers
        )
        return {"value": data, "source": "CoinGlass v4 funding-rate oi-weight-history", "timestamp": now_iso()}
    except Exception as e:
        return {"value": None, "source": "CoinGlass", "error": str(e), "timestamp": now_iso()}

async def coin_snapshot(symbol: str, market_row: dict[str, Any]) -> dict[str, Any]:
    ohlc = []
    indicator_errors = []
    try:
        days = 400 if symbol == "BTC" else 90
        ohlc = await coingecko_ohlc(symbol, days=days)
    except Exception as e:
        indicator_errors.append(f"ohlc_error:{e}")
    closes = [x["close"] for x in ohlc]
    return {
        **market_row,
        "rsi_14d": rsi(closes, 14) if closes else None,
        "atr_14d": atr(ohlc, 14) if ohlc else None,
        "funding": await coinglass_funding(symbol) if symbol in ["BTC", "XRP", "ONDO"] else {"value": None, "source": "CoinGlass", "error": "no_perp_or_not_configured", "timestamp": now_iso()},
        "indicator_errors": indicator_errors
    }

async def build_exit_snapshot() -> dict[str, Any]:
    markets = await coingecko_market_data()
    coins = {}
    for sym in ["XRP", "ONDO", "AERO", "CFG"]:
        coins[sym] = await coin_snapshot(sym, markets.get(sym, {}))

    btc_ohlc = await coingecko_ohlc("BTC", days=400)
    btc_closes = [x["close"] for x in btc_ohlc]
    btc = await coin_snapshot("BTC", markets.get("BTC", {}))
    btc["pi_cycle"] = pi_cycle_status(btc_closes)

    return {
        "schema_version": "1.0.0",
        "timestamp": now_iso(),
        "sources": {
            "spot_ohlc_volume": "CoinGecko",
            "btc_dominance": "CoinGecko global market data",
            "fear_greed": "alternative.me",
            "cbbi": "CBBI.info scrape/fallback",
            "funding_oi": "CoinGlass if COINGLASS_API_KEY configured"
        },
        "btc": btc,
        "btc_dominance": await btc_global_dominance(),
        "cbbi": await cbbi_score(),
        "fear_greed": await fear_greed(),
        "coins": coins,
        "data_quality": {
            "coinglass_enabled": bool(settings.coinglass_api_key),
            "coingecko_key_enabled": bool(settings.coingecko_api_key),
            "notes": [
                "Funding/OI staat op null zonder CoinGlass API-key.",
                "CBBI scrape kan breken als de site-layout wijzigt.",
                "GPT moet ontbrekende waarden als ⚪ markeren."
            ]
        }
    }
