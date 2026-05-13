from datetime import datetime, timezone
import httpx

from .indicators import calculate_rsi, calculate_atr

CACHE = {
    "snapshot": None,
    "timestamp": None
}

COINS = {
    "XRP": "ripple",
    "ONDO": "ondo-finance",
    "AERO": "aerodrome-finance",
    "CFG": "centrifuge"
}


def now_iso():
    return datetime.now(timezone.utc).isoformat()


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
        response.raise_for_status()
        return response.json()


async def build_exit_snapshot():
    # Gebruik cache om CoinGecko 429 rate limits te beperken
    if CACHE["snapshot"] is not None:
        return CACHE["snapshot"]

    try:
        prices = await get_prices()

        coins = {}

        for symbol, coin_id in COINS.items():
            base = prices.get(coin_id, {})

            indicators = {
                "rsi_14d": None,
                "atr_14d": None,
                "atr_method": "disabled_rate_limit"
            }

            coins[symbol] = {
                **base,
                **indicators
            }

        snapshot = {
            "timestamp": now_iso(),
            "status": "ok",
            "source": "exit-data-pipeline",
            "coins": coins,
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
        CACHE["timestamp"] = now_iso()

        return snapshot

    except Exception as e:
        if CACHE["snapshot"]:
            cached = CACHE["snapshot"]
            cached["cache_used"] = True
            cached["api_error"] = str(e)
            return cached

        return {
            "timestamp": now_iso(),
            "status": "degraded",
            "source": "exit-data-pipeline",
            "api_error": str(e),
            "coins": {},
            "btc": {},
            "missing_data": ["live_market_data"]
        }
