from datetime import datetime, timezone
import httpx

from .indicators import calculate_rsi, calculate_atr

CACHE = {
    "snapshot": None
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


async def get_market_chart(coin_id):
    url = f"https://api.coingecko.com/api/v3/coins/{coin_id}/market_chart"
    params = {
        "vs_currency": "usd",
        "days": "30",
        "interval": "daily"
    }

    async with httpx.AsyncClient(timeout=20) as client:
        response = await client.get(url, params=params)
        response.raise_for_status()
        data = response.json()

    prices = data.get("prices", [])
    closes = [p[1] for p in prices]

    # CoinGecko market_chart geeft geen echte high/low candles.
    # Voor v0.3 gebruiken we close-proxy ATR.
    highs = closes
    lows = closes

    return {
        "rsi_14d": calculate_rsi(closes),
        "atr_14d": calculate_atr(highs, lows, closes),
        "atr_method": "close_proxy"
    }


async def build_exit_snapshot():
    try:
        prices = await get_prices()

        coins = {}

        for symbol, coin_id in COINS.items():
            base = prices.get(coin_id, {})
            try:
                indicators = await get_market_chart(coin_id)
            except Exception as e:
                indicators = {
                    "rsi_14d": None,
                    "atr_14d": None,
                    "atr_method": "unavailable",
                    "indicator_error": str(e)
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
                "open_interest"
            ]
        }

        CACHE["snapshot"] = snapshot
        return snapshot

    except Exception as e:
        if CACHE["snapshot"]:
            cached = CACHE["snapshot"]
            cached["api_error"] = str(e)
            cached["cache_used"] = True
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
