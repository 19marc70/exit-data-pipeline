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
    return (
        CACHE["snapshot"] is not None
        and time.time() - CACHE["timestamp"] < CACHE_TTL_SECONDS
    )


async def get_prices():
    url = "https://api.coingecko.com/api/v3/simple/price"

    params = {
        "ids": ",".join(COINS.values()),
        "vs_currencies": "usd",
        "include_market_cap": "true",
        "include_24hr_vol": "true",
        "include_24hr_change": "true"
    }

    try:
        async with httpx.AsyncClient(timeout=20) as client:
            response = await client.get(url, params=params)

            if response.status_code == 429:
                if CACHE["snapshot"]:
                    return CACHE["snapshot"].get("raw_prices", {})
                return {}

            response.raise_for_status()
            return response.json()

    except Exception:
        if CACHE["snapshot"]:
            return CACHE["snapshot"].get("raw_prices", {})
        return {}


async def build_exit_snapshot():
    if cache_valid():
        return CACHE["snapshot"]

    prices = await get_prices()

    if not prices:
        return {
            "timestamp": now_iso(),
            "status": "degraded",
            "source": "exit-data-pipeline",
            "api_error": "coingecko_unavailable_or_rate_limited",
            "coins": {},
            "btc": {},
            "missing_data": ["live_market_data"]
        }

    coins = {}

    for symbol, coin_id in COINS.items():
        base = prices.get(coin_id, {})
        coins[symbol] = {
            **base,
            "rsi_14d": None,
            "atr_14d": None,
            "atr_method": "disabled_free_rate_limit_mode"
        }

    snapshot = {
        "timestamp": now_iso(),
        "status": "ok",
        "source": "exit-data-pipeline",
        "cache_ttl_seconds": CACHE_TTL_SECONDS,
        "free_rate_limit_mode": True,
        "coins": coins,
        "raw_prices": prices,
        "btc": {
            "dominance": None,
            "cbbi": None,
            "pi_cycle": {
                "status": "unknown",
                "distance_pct": None
            }
        },
        "missing_data": [
            "btc_dominance",
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
