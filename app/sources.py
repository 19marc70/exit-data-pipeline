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

    async with httpx.AsyncClient(timeout=20) as client:
        response = await client.get(url, params=params)
        if response.status_code == 429:
            return CACHE["snapshot"].get("raw_prices", {}) if CACHE["snapshot"] else {}
        response.raise_for_status()
        return response.json()


async def get_btc_dominance():
    try:
        url = "https://api.coingecko.com/api/v3/global"
        async with httpx.AsyncClient(timeout=20) as client:
            response = await client.get(url)
            if response.status_code == 429:
                return None
            response.raise_for_status()
            data = response.json()
            return data.get("data", {}).get("market_cap_percentage", {}).get("btc")
    except Exception:
        return None


async def get_fear_greed():
    try:
        url = "https://api.alternative.me/fng/"
        async with httpx.AsyncClient(timeout=20) as client:
            response = await client.get(url)
            response.raise_for_status()
            data = response.json()
            item = data.get("data", [{}])[0]
            return {
                "value": int(item.get("value")),
                "classification": item.get("value_classification")
            }
    except Exception:
        return None


async def build_exit_snapshot():
    if cache_valid():
        return CACHE["snapshot"]

    prices = await get_prices()
    btc_dominance = await get_btc_dominance()
    fear_greed = await get_fear_greed()

    if not prices:
        return {
            "timestamp": now_iso(),
            "status": "degraded",
            "source": "exit-data-pipeline",
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
            "atr_method": "disabled_free_rate_limit_mode"
        }

    missing_data = [
        "cbbi",
        "pi_cycle",
        "funding",
        "open_interest",
        "rsi",
        "atr"
    ]

    if btc_dominance is None:
        missing_data.append("btc_dominance")

    if fear_greed is None:
        missing_data.append("fear_greed")

    snapshot = {
        "timestamp": now_iso(),
        "status": "ok",
        "source": "exit-data-pipeline",
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
        "missing_data": missing_data
    }

    CACHE["snapshot"] = snapshot
    CACHE["timestamp"] = time.time()

    return snapshot
