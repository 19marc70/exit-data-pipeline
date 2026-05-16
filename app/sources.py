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
    "XRP": "XRPUSDT",
    "ONDO": "ONDOUSDT",
    "AERO": "AEROUSDT",
    "CFG": "CFGUSDT"
}

HYPERLIQUID_SYMBOLS = {
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


async def post_json(url, payload=None, headers=None):
    try:
        async with httpx.AsyncClient(timeout=25) as client:
            response = await client.post(url, json=payload, headers=headers)

            if response.status_code == 429:
                print(f"RATE LIMIT HIT: {url}")
                return None

            if response.status_code in [401, 403]:
                print(f"AUTH/BLOCK ERROR {response.status_code}: {url}")
                return None

            response.raise_for_status()
            return response.json()

    except Exception as e:
        print(f"HTTP POST ERROR: {url} -> {e}")
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
    data = await get_json("https://api.coingecko.com/api/v3/global")

    if not data:
        return None

    return data.get("data", {}).get("market_cap_percentage", {}).get("btc")


async def get_btc_price_history():
    data = await get_json(
        "https://api.coingecko.com/api/v3/coins/bitcoin/market_chart",
        {
            "vs_currency": "usd",
            "days": "420",
            "interval": "daily"
        }
    )

    if not data:
        return []

    prices = data.get("prices", [])
    closes = []

    for item in prices:
        if isinstance(item, list) and len(item) >= 2:
            closes.append(float(item[1]))

    return closes


def calculate_pi_cycle(closes):
    if not closes or len(closes) < 350:
        return {
            "status": "unknown",
            "cycle_state": "⚪ insufficient_history",
            "distance_pct": None,
            "ma_111": None,
            "ma_350x2": None,
            "top_risk": False,
            "method": "pi_cycle_111dma_vs_350dma_x2"
        }

    ma_111 = sum(closes[-111:]) / 111
    ma_350 = sum(closes[-350:]) / 350
    ma_350x2 = ma_350 * 2

    distance_pct = ((ma_350x2 - ma_111) / ma_111) * 100

    if distance_pct <= 0:
        status = "top_risk"
        cycle_state = "🔴 TOP_RISK"
        top_risk = True
    elif distance_pct <= 10:
        status = "late_cycle"
        cycle_state = "🟠 LATE_CYCLE"
        top_risk = False
    elif distance_pct <= 25:
        status = "mid_late_cycle"
        cycle_state = "🟡 MID_LATE_CYCLE"
        top_risk = False
    else:
        status = "early_mid_cycle"
        cycle_state = "🟢 EARLY_MID_CYCLE"
        top_risk = False

    return {
        "status": status,
        "cycle_state": cycle_state,
        "distance_pct": round(distance_pct, 2),
        "ma_111": round(ma_111, 2),
        "ma_350x2": round(ma_350x2, 2),
        "top_risk": top_risk,
        "method": "pi_cycle_111dma_vs_350dma_x2"
    }


async def get_fear_greed():
    data = await get_json("https://api.alternative.me/fng/")

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
            "reason": "missing_api_key",
            "value": None,
            "source": "coinglass"
        }

    headers = {"CG-API-KEY": COINGLASS_API_KEY}

    data = await get_json(
        "https://open-api-v4.coinglass.com/api/futures/funding-rate/oi-weight-history",
        {"symbol": symbol},
        headers=headers
    )

    if not data:
        return {
            "available": False,
            "reason": "api_unavailable",
            "value": None,
            "source": "coinglass"
        }

    try:
        rows = data.get("data")

        if isinstance(rows, dict):
            rows = rows.get("list", [])

        if not rows:
            return {
                "available": False,
                "reason": "empty_response",
                "value": None,
                "source": "coinglass"
            }

        last = rows[-1]
        funding = None

        if isinstance(last, list):
            funding = float(last[-1])

        elif isinstance(last, dict):
            for key in ["close", "fundingRate", "funding_rate", "rate", "value"]:
                if last.get(key) is not None:
                    funding = float(last.get(key))
                    break

        return {
            "available": funding is not None,
            "reason": "ok" if funding is not None else "funding_parse_failed",
            "value": funding,
            "source": "coinglass"
        }

    except Exception as e:
        return {
            "available": False,
            "reason": f"parse_error:{str(e)}",
            "value": None,
            "source": "coinglass"
        }


async def get_coinglass_open_interest(symbol):
    if not COINGLASS_API_KEY:
        return {
            "available": False,
            "reason": "missing_api_key",
            "value": None,
            "change_24h_pct": None,
            "source": "coinglass"
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
            "reason": "api_unavailable",
            "value": None,
            "change_24h_pct": None,
            "source": "coinglass"
        }

    try:
        rows = data.get("data")

        if isinstance(rows, dict):
            rows = rows.get("list", [])

        if not rows or len(rows) < 2:
            return {
                "available": False,
                "reason": "not_enough_history",
                "value": None,
                "change_24h_pct": None,
                "source": "coinglass"
            }

        def extract_value(row):
            if isinstance(row, list):
                return float(row[-1])

            if isinstance(row, dict):
                for key in ["close", "openInterest", "open_interest", "oi", "value"]:
                    if row.get(key) is not None:
                        return float(row.get(key))

            return None

        current_value = extract_value(rows[-1])
        previous_value = extract_value(rows[-2])

        if current_value is None or previous_value in [None, 0]:
            return {
                "available": False,
                "reason": "oi_parse_failed",
                "value": None,
                "change_24h_pct": None,
                "source": "coinglass"
            }

        change_pct = ((current_value - previous_value) / previous_value) * 100

        return {
            "available": True,
            "reason": "ok",
            "value": current_value,
            "change_24h_pct": round(change_pct, 2),
            "source": "coinglass"
        }

    except Exception as e:
        return {
            "available": False,
            "reason": f"parse_error:{str(e)}",
            "value": None,
            "change_24h_pct": None,
            "source": "coinglass"
        }


async def get_hyperliquid_contexts():
    data = await post_json(
        "https://api.hyperliquid.xyz/info",
        {"type": "metaAndAssetCtxs"},
        {"Content-Type": "application/json"}
    )

    if not data:
        return {}

    try:
        meta = data[0]
        asset_contexts = data[1]
        universe = meta.get("universe", [])

        result = {}

        for index, asset in enumerate(universe):
            name = asset.get("name")
            ctx = asset_contexts[index] if index < len(asset_contexts) else {}

            if name:
                result[name.upper()] = ctx

        return result

    except Exception as e:
        print(f"HYPERLIQUID PARSE ERROR: {e}")
        return {}


def get_hyperliquid_derivatives(symbol, contexts):
    hl_symbol = HYPERLIQUID_SYMBOLS.get(symbol)

    if not hl_symbol:
        return {
            "funding": {
                "available": False,
                "reason": "missing_hyperliquid_symbol",
                "value": None,
                "source": "hyperliquid"
            },
            "open_interest": {
                "available": False,
                "reason": "missing_hyperliquid_symbol",
                "value": None,
                "change_24h_pct": None,
                "source": "hyperliquid"
            }
        }

    ctx = contexts.get(hl_symbol.upper())

    if not ctx:
        return {
            "funding": {
                "available": False,
                "reason": "hyperliquid_symbol_not_listed",
                "value": None,
                "source": "hyperliquid"
            },
            "open_interest": {
                "available": False,
                "reason": "hyperliquid_symbol_not_listed",
                "value": None,
                "change_24h_pct": None,
                "source": "hyperliquid"
            }
        }

    funding_value = None
    oi_value = None

    try:
        if ctx.get("funding") is not None:
            funding_value = float(ctx.get("funding"))
    except Exception:
        funding_value = None

    try:
        if ctx.get("openInterest") is not None:
            oi_value = float(ctx.get("openInterest"))
    except Exception:
        oi_value = None

    return {
        "funding": {
            "available": funding_value is not None,
            "reason": "ok" if funding_value is not None else "funding_missing",
            "value": funding_value,
            "source": "hyperliquid"
        },
        "open_interest": {
            "available": oi_value is not None,
            "reason": "ok" if oi_value is not None else "oi_missing",
            "value": oi_value,
            "change_24h_pct": None,
            "source": "hyperliquid"
        }
    }


def classify_derivatives(funding, open_interest):
    funding_value = funding.get("value") if isinstance(funding, dict) else None
    oi_change = open_interest.get("change_24h_pct") if isinstance(open_interest, dict) else None
    oi_available = open_interest.get("available") if isinstance(open_interest, dict) else False

    leverage_risk = "⚪ unknown"
    reasons = []

    if funding_value is not None:
        if funding_value >= 0.0008:
            leverage_risk = "🔴 overheated_longs"
            reasons.append("funding_extreme_positive")
        elif funding_value >= 0.0003:
            leverage_risk = "🟠 crowded_longs"
            reasons.append("funding_positive")
        elif funding_value <= -0.0003:
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

    elif oi_available:
        reasons.append("oi_available_no_24h_change")

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
    btc_history = await get_btc_price_history()
    pi_cycle = calculate_pi_cycle(btc_history)
    hyperliquid_contexts = await get_hyperliquid_contexts()

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

        derivative_source_priority = "coinglass"

        if not funding.get("available") or not open_interest.get("available"):
            fallback = get_hyperliquid_derivatives(symbol, hyperliquid_contexts)

            if not funding.get("available") and fallback["funding"].get("available"):
                funding = fallback["funding"]
                derivative_source_priority = "hyperliquid_fallback"

            if not open_interest.get("available") and fallback["open_interest"].get("available"):
                open_interest = fallback["open_interest"]
                derivative_source_priority = "hyperliquid_fallback"

        derivatives_state = classify_derivatives(funding, open_interest)

        coins[symbol] = {
            **base,
            "rsi_14d": rsi,
            "atr_14d": atr,
            "volatility": volatility,
            "trend": classify_trend(change_24h),
            "indicator_method": "synthetic_proxy_model",
            "derivatives": {
                "source_priority": derivative_source_priority,
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
        "hyperliquid_fallback_enabled": True,
        "cycle_intelligence_enabled": True,
        "coins": coins,
        "btc": {
            "dominance": btc_dominance,
            "fear_greed": fear_greed,
            "altseason_index": altseason_index,
            "stablecoin_regime": stablecoin_regime,
            "cbbi": None,
            "pi_cycle": pi_cycle
        },
        "missing_data": [
            "cbbi"
        ]
    }

    CACHE["snapshot"] = snapshot
    CACHE["timestamp"] = time.time()

    return snapshot
