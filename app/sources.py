import os
import time
import httpx
from datetime import datetime, timezone

CACHE = {
    "snapshot": {
        "timestamp": "bootstrap",
        "status": "bootstrap_cache",
        "coins": {},
        "btc": {}
    },
    "timestamp": 0
}

CACHE_TTL_SECONDS = int(os.getenv("CACHE_TTL_SECONDS", "7200"))
COINGLASS_API_KEY = os.getenv("COINGLASS_API_KEY")

COINS = {
    "XRP": "ripple",
    "ONDO": "ondo-finance",
    "AERO": "aerodrome-finance",
    "CFG": "centrifuge"
}

DERIVATIVE_SYMBOLS = {
    "XRP": "XRP",
    "ONDO": "ONDO",
    "AERO": "AERO",
    "CFG": "CFG"
}


def now_iso():
    return datetime.now(timezone.utc).isoformat()


def cache_valid():
    return (
        CACHE["snapshot"] is not None
        and time.time() - CACHE["timestamp"] < CACHE_TTL_SECONDS
    )


async def get_json(url, params=None, headers=None):
    try:
        async with httpx.AsyncClient(timeout=25) as client:
            response = await client.get(url, params=params, headers=headers)

            if response.status_code == 429:
                print(f"RATE LIMIT HIT: {url}")
                return None

            if response.status_code in [401, 403]:
                print(f"AUTH/BLOCK ERROR {response.status_code}: {url}")
                return None

            response.raise_for_status()
            return response.json()

    except Exception as e:
        print(f"HTTP ERROR: {url} -> {e}")
        return None


def classify_trend(change_24h):
    if change_24h is None:
        return "⚪ unknown"
    if change_24h >= 5:
        return "🟢 strengthening"
    if change_24h <= -5:
        return "🟠 weakening"
    return "🟡 sideways"


def synthetic_rsi(change_24h):
    if change_24h is None:
        return 50
    base = 50 + (change_24h * 3)
    return round(max(5, min(95, base)), 2)


def synthetic_atr(price, change_24h):
    if price is None or change_24h is None:
        return 0
    volatility_factor = abs(change_24h) / 100
    atr = price * volatility_factor
    return round(atr, 6)


def classify_volatility(price, atr):
    if price is None or atr is None or price == 0:
        return "⚪ unavailable"

    atr_pct = (atr / price) * 100

    if atr_pct >= 10:
        return "🔴 high"
    if atr_pct >= 5:
        return "🟠 elevated"
    if atr_pct >= 2:
        return "🟡 medium"

    return "🟢 low"


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
    data = await get_json(
        "https://api.coingecko.com/api/v3/global"
    )

    if not data:
        return None

    return data.get("data", {}).get("market_cap_percentage", {}).get("btc")


async def get_fear_greed():
    data = await get_json(
        "https://api.alternative.me/fng/"
    )

    if not data:
        return {
            "value": None,
            "classification": "unknown"
        }

    item = data.get("data", [{}])[0]

    try:
        value = int(item.get("value"))
    except Exception:
        value = None

    return {
        "value": value,
        "classification": item.get("value_classification")
    }


async def get_coinglass_funding(symbol):
    if not COINGLASS_API_KEY:
        return {
            "available": False,
            "reason": "missing_coinglass_api_key",
            "value": None
        }

    headers = {"CG-API-KEY": COINGLASS_API_KEY}

    data = await get_json(
        "https://open-api-v4.coinglass.com/api/futures/funding-rate/oi-weight-history",
        {
            "symbol": symbol
        },
        headers=headers
    )

    if not data:
        return {
            "available": False,
            "reason": "coinglass_funding_unavailable",
            "value": None
        }

    try:
        rows = data.get("data", [])
        if isinstance(rows, dict):
            rows = rows.get("list", [])

        last = rows[-1] if rows else None

        value = None
        if isinstance(last, dict):
            value = (
                last.get("close")
                or last.get("fundingRate")
                or last.get("funding_rate")
                or last.get("value")
            )
        elif isinstance(last, list) and len(last) > 1:
            value = last[-1]

        return {
            "available": value is not None,
            "reason": "ok" if value is not None else "funding_parse_failed",
            "value": float(value) if value is not None else None
        }

    except Exception as e:
        return {
            "available": False,
            "reason": f"funding_parse_error:{e}",
            "value": None
        }


async def get_coinglass_open_interest(symbol):
    if not COINGLASS_API_KEY:
        return {
            "available": False,
            "reason": "missing_coinglass_api_key",
            "value": None
        }

    headers = {"CG-API-KEY": COINGLASS_API_KEY}

    data = await get_json(
        "https://open-api-v4.coinglass.com/api/futures/openInterest/ohlc-history",
        {
            "symbol": symbol,
            "interval": "1d",
            "limit": "2"
        },
        headers=headers
    )

    if not data:
        return {
            "available": False,
            "reason": "coinglass_oi_unavailable",
            "value": None,
            "change_24h_pct": None
        }

    try:
        rows = data.get("data", [])
        if isinstance(rows, dict):
            rows = rows.get("list", [])

        if not rows:
            return {
                "available": False,
                "reason": "oi_empty",
                "value": None,
                "change_24h_pct": None
            }

        def extract_close(row):
            if isinstance(row, dict):
                return (
                    row.get("close")
                    or row.get("openInterest")
                    or row.get("open_interest")
                    or row.get("value")
                )
            if isinstance(row, list) and len(row) > 1:
                return row[-1]
            return None

        last_value = extract_close(rows[-1])
        prev_value = extract_close(rows[-2]) if len(rows) >= 2 else None

        change_pct = None
        if last_value is not None and prev_value not in [None, 0]:
            change_pct = ((float(last_value) - float(prev_value)) / float(prev_value)) * 100

        return {
            "available": last_value is not None,
            "reason": "ok" if last_value is not None else "oi_parse_failed",
            "value": float(last_value) if last_value is not None else None,
            "change_24h_pct": round(change_pct, 2) if change_pct is not None else None
        }

    except Exception as e:
        return {
            "available": False,
            "reason": f"oi_parse_error:{e}",
            "value": None,
            "change_24h_pct": None
        }


def classify_derivatives(funding, open_interest):
    funding_value = funding.get("value") if isinstance(funding, dict) else None
    oi_change = open_interest.get("change_24h_pct") if isinstance(open_interest, dict) else None

    leverage_risk = "⚪ unknown"
    reasons = []

    if funding_value is not None:
        if funding_value >= 0.08:
            leverage_risk = "🔴 overheated_longs"
            reasons.append("funding_extreme_positive")
        elif funding_value >= 0.03:
            leverage_risk = "🟠 crowded_longs"
            reasons.append("funding_positive")
        elif funding_value <= -0.03:
            leverage_risk = "🟢 short_pressure"
            reasons.append("funding_negative")
        else:
            leverage_risk = "🟡 neutral_funding"
            reasons.append("funding_neutral")
    else:
        reasons.append("funding_missing")

    if oi_change is not None:
        if oi_change >= 15:
            reasons.append("oi_expansion")
            if leverage_risk in ["🟠 crowded_longs", "🔴 overheated_longs"]:
                leverage_risk = "🔴 leverage_overheat"
        elif oi_change <= -15:
            reasons.append("oi_flush")
        else:
            reasons.append("oi_stable")
    else:
        reasons.append("oi_missing")

    return {
        "leverage_risk": leverage_risk,
        "reasons": reasons
    }


async def build_exit_snapshot():
    if cache_valid():
        cached = CACHE["snapshot"].copy()
        cached["cache_mode"] = "fresh_cache"
        return cached

    prices = await get_prices()
    btc_dominance = await get_btc_dominance()
    fear_greed = await get_fear_greed()

    if not prices:
        cached = CACHE["snapshot"].copy()
        cached["timestamp"] = now_iso()
        cached["status"] = "degraded"
        cached["cache_mode"] = "fallback_cache_active"
        cached["api_error"] = "coingecko_unavailable"
        return cached

    coins = {}

    for symbol, coin_id in COINS.items():
        base = prices.get(coin_id, {})

        price = base.get("usd", 0)
        change_24h = base.get("usd_24h_change", 0)

        rsi = synthetic_rsi(change_24h)
        atr = synthetic_atr(price, change_24h)
        volatility = classify_volatility(price, atr)

        derivative_symbol = DERIVATIVE_SYMBOLS.get(symbol)

        funding = await get_coinglass_funding(derivative_symbol)
        open_interest = await get_coinglass_open_interest(derivative_symbol)
        derivatives_state = classify_derivatives(funding, open_interest)

        coins[symbol] = {
            **base,
            "rsi_14d": rsi,
            "atr_14d": atr,
            "volatility": volatility,
            "trend": classify_trend(change_24h),
            "indicator_method": "synthetic_proxy_model",
            "derivatives": {
                "funding": funding,
                "open_interest": open_interest,
                "state": derivatives_state
            }
        }

    altseason_index = None
    stablecoin_regime = "🟡 neutral"

    if btc_dominance is not None:
        altseason_index = round(max(0, 100 - btc_dominance), 2)

    if fear_greed.get("value") is not None:
        fg = fear_greed["value"]

        if fg <= 25:
            stablecoin_regime = "🟢 defensive_rotation"
        elif fg >= 75:
            stablecoin_regime = "🔴 euphoric_risk"

    snapshot = {
        "timestamp": now_iso(),
        "status": "ok",
        "source": "exit-data-pipeline",
        "cache_mode": "live",
        "cache_ttl_seconds": CACHE_TTL_SECONDS,
        "coinglass_enabled": bool(COINGLASS_API_KEY),
        "coins": coins,
        "btc": {
            "dominance": btc_dominance,
            "fear_greed": fear_greed,
            "altseason_index": altseason_index,
            "stablecoin_regime": stablecoin_regime,
            "cbbi": None,
            "pi_cycle": {
                "status": "unknown",
                "distance_pct": None
            }
        },
        "missing_data": [
            "cbbi",
            "pi_cycle"
        ]
    }

    CACHE["snapshot"] = snapshot
    CACHE["timestamp"] = time.time()

    return snapshot
