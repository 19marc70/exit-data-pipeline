from datetime import datetime, timezone
import os
import time
import httpx

CACHE = {
    "snapshot": None,
    "timestamp": 0
}

COINS = {
    "XRP": "ripple",
    "ONDO": "ondo-finance",
    "AERO": "aerodrome-finance",
    "CFG": "centrifuge"
}

CACHE_TTL_SECONDS = int(os.getenv("CACHE_TTL_SECONDS", "3600"))

def now_iso():
    return datetime.now(timezone.utc).isoformat()

def cache_valid():
    return CACHE["snapshot"] is not None and time.time() - CACHE["timestamp"] < CACHE_TTL_SECONDS

async def get_json(url, params=None):
    try:
        async with httpx.AsyncClient(timeout=25) as client:
            r = await client.get(url, params=params)
            if r.status_code == 429:
                return None
            r.raise_for_status()
            return r.json()
    except Exception:
        return None

async def get_prices():
    return await get_json(
        "https://api.coingecko.com/api/v3/simple/price",
        {
            "ids": ",".join(COINS.values()),
            "vs_currencies": "usd",
            "include_market_cap": "true",
            "include_24hr_vol": "true",
            "include_24hr_change": "true"
        }
    )

async def get_btc_dominance():
    data = await get_json("https://api.coingecko.com/api/v3/global")
    if not data:
        return None
    return data.get("data", {}).get("market_cap_percentage", {}).get("btc")

async def get_fear_greed():
    data = await get_json("https://api.alternative.me/fng/")
    if not data:
        return None
    item = data.get("data", [{}])[0]
    return {
        "value": int(item.get("value")),
        "classification": item.get("value_classification")
    }

async def build_exit_snapshot():
    if cache_valid():
        cached = CACHE["snapshot"].copy()
        cached["cache_mode"] = "fresh_cache"
        return cached

    prices = await get_prices()
    btc_dominance = await get_btc_dominance()
    fear_greed = await get_fear_greed()

    if not prices and CACHE["snapshot"]:
        cached = CACHE["snapshot"].copy()
        cached["timestamp"] = now_iso()
        cached["status"] = "degraded"
        cached["cache_mode"] = "fallback_active"
        cached["api_error"] = "coingecko_rate_limited_using_cached_data"
        return cached

    if not prices:
        return {
            "timestamp": now_iso(),
            "status": "degraded",
            "source": "exit-data-pipeline",
            "cache_mode": "no_cache_available",
            "api_error": "coingecko_unavailable_or_rate_limited",
            "coins": {},
            "btc": {
                "dominance": btc_dominance,
                "fear_greed": fear_greed
            },
            "missing_data": ["live_market_data"]
        }

    coins = {}

    for symbol, coin_id in COINS.items():
        base = prices.get(coin_id, {})
        coins[symbol] = {
            **base,
            "rsi_14d": None,
            "atr_14d": None,
            "trend": "⚪ unavailable",
            "atr_method": "disabled_free_rate_limit_mode"
        }

    snapshot = {
        "timestamp": now_iso(),
        "status": "ok",
        "source": "exit-data-pipeline",
        "cache_mode": "live",
        "cache_ttl_seconds": CACHE_TTL_SECONDS,
        "free_rate_limit_mode": True,
        "coins": coins,
        "raw_prices": prices,
        "btc": {
            "dominance": btc_dominance,
            "fear_greed": fear_greed,
            "cbbi": None,
            "pi_cycle": {
                "status": "unknown",
                "distance_pct": None
            }
        },
        "missing_data": [
            "cbbi",
            "pi_cycle",
            "funding",
            "open_interest",
            "rsi",
            "atr"
        ]
    }

    CACHE["snapshot"] = snapshot
    CACHE["timestamp"] = time.time()

    return snapshot
