from datetime import datetime, timezone
import httpx

def now_iso():
    return datetime.now(timezone.utc).isoformat()

async def get_prices():
    url = "https://api.coingecko.com/api/v3/simple/price"

    params = {
        "ids": "ripple,ondo-finance,aerodrome-finance,centrifuge",
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
    prices = await get_prices()

    return {
        "timestamp": now_iso(),
        "status": "ok",
        "source": "exit-data-pipeline",
        "coins": {
            "XRP": prices.get("ripple", {}),
            "ONDO": prices.get("ondo-finance", {}),
            "AERO": prices.get("aerodrome-finance", {}),
            "CFG": prices.get("centrifuge", {})
        },
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
            "rsi",
            "atr",
            "funding",
            "open_interest"
        ]
    }
