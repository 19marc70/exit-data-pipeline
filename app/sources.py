from datetime import datetime, timezone
import os
import time
import httpx

from .indicators import calculate_rsi, calculate_atr_proxy, classify_trend

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


async def get_json(url, params=None):
    async with httpx.AsyncClient(timeout=25) as client:
        response = await client.get(url, params=params)
        if response.status_code == 429:
            return None
        response.raise_for_status()
        return response.json()


async def get_prices():
    url = "https://api.coingecko.com/api/v3/simple/price"
    params = {
        "ids": ",".join(COINS.values()),
        "vs_currencies": "usd",
        "include_market_cap": "true",
        "include_24hr_vol": "true",
        "include_24hr_change": "true"
    }
    return await get_json(url, params)


async def get_market_chart(coin_id):
    url = f"https://api.coingecko.com/api/v3/coins/{coin_id}/market_chart"
    params = {
        "vs_currency": "usd",
        "days": "30",
        "interval": "daily"
    }

    data = await get_json(url, params)

    if not data:
        return {
            "rsi_14d": None,
            "atr_14d": None,
            "trend": "⚪ unavailable",
            "atr_method": "unavailable_rate_limit"
        }

    prices = data.get("prices", [])
    closes = [item[1] for item in prices]

    return {
        "rsi_14d": calculate_rsi(closes),
        "atr_14d": calculate_atr_proxy(closes),
        "trend": classify_trend(closes),
        "atr_method": "close_to_close_proxy"
    }


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

    try:
        value = int(item.get("value"))
    except Exception:
        value = None

    return {
        "value": value,
        "classification": item.get("value_classification")
    }


async def build_exit_snapshot():
    if cache_valid():
        return CACHE["snapshot"]

    prices = await get_prices()
    btc_dominance = await get_btc_dominance()
    fear_greed = await get_fear_greed()

    if not prices:
        if CACHE["snapshot"]:
            cached = CACHE["snapshot"]
            cached["cache_used"] = True
            cached["api_error"] = "coingecko_rate_limited"
            return cached

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
        indicators = await get_market_chart(coin_id)

        coins[symbol] = {
            **base,
            **indicators
        }

    missing_data = [
        "cbbi",
        "pi_cycle",
        "funding",
        "open_interest"
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
