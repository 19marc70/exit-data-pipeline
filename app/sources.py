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
    return CACHE["snapshot"] is not None and time.time() - CACHE["timestamp"] < CACHE_TTL_SECONDS


async def get_json(url, params=None, headers=None):
    try:
        async with httpx.AsyncClient(timeout=25) as client:
            r = await client.get(url, params=params, headers=headers)

            if r.status_code in [401, 403, 429]:
                print(f"HTTP BLOCK/RATE {r.status_code}: {url}")
                return None

            r.raise_for_status()
            return r.json()

    except Exception as e:
        print(f"HTTP ERROR: {url} -> {e}")
        return None


async def post_json(url, payload=None, headers=None):
    try:
        async with httpx.AsyncClient(timeout=25) as client:
            r = await client.post(url, json=payload, headers=headers)

            if r.status_code in [401, 403, 429]:
                print(f"HTTP POST BLOCK/RATE {r.status_code}: {url}")
                return None

            r.raise_for_status()
            return r.json()

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

    return round(max(5, min(95, 50 + change_24h * 3)), 2)


def synthetic_atr(price, change_24h):
    if price is None or change_24h is None:
        return 0

    return round(price * abs(change_24h) / 100, 6)


def classify_volatility(price, atr):
    if price is None or atr is None or price == 0:
        return "⚪ unavailable"

    atr_pct = atr / price * 100

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
            "include_24hr_change": "true",
        },
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
        },
    )

    if not data:
        return []

    return [
        float(x[1])
        for x in data.get("prices", [])
        if isinstance(x, list) and len(x) >= 2
    ]


def calculate_pi_cycle(closes):
    if not closes or len(closes) < 350:
        return {
            "status": "unknown",
            "cycle_state": "⚪ insufficient_history",
            "distance_pct": None,
            "ma_111": None,
            "ma_350x2": None,
            "top_risk": False,
            "method": "pi_cycle_111dma_vs_350dma_x2",
        }

    ma_111 = sum(closes[-111:]) / 111
    ma_350x2 = (sum(closes[-350:]) / 350) * 2
    distance_pct = ((ma_350x2 - ma_111) / ma_111) * 100

    if distance_pct <= 0:
        status = "top_risk"
        state = "🔴 TOP_RISK"
        top_risk = True
    elif distance_pct <= 10:
        status = "late_cycle"
        state = "🟠 LATE_CYCLE"
        top_risk = False
    elif distance_pct <= 25:
        status = "mid_late_cycle"
        state = "🟡 MID_LATE_CYCLE"
        top_risk = False
    else:
        status = "early_mid_cycle"
        state = "🟢 EARLY_MID_CYCLE"
        top_risk = False

    return {
        "status": status,
        "cycle_state": state,
        "distance_pct": round(distance_pct, 2),
        "ma_111": round(ma_111, 2),
        "ma_350x2": round(ma_350x2, 2),
        "top_risk": top_risk,
        "method": "pi_cycle_111dma_vs_350dma_x2",
    }


async def get_cbbi():
    data = await get_json(
        "https://colintalkscrypto.com/cbbi/data/latest.json"
    )

    if not data:
        return {
            "available": False,
            "value": None,
            "state": "⚪ unavailable",
            "reason": "cbbi_endpoint_unavailable",
            "source": "colintalkscrypto",
        }

    try:
        value = None

        keys = [
            "CBBI",
            "cbbi",
            "value",
            "confidence",
            "Confidence",
            "index"
        ]

        subkeys = [
            "value",
            "current",
            "score",
            "confidence",
            "Confidence"
        ]

        if isinstance(data, dict):
            for key in keys:
                raw = data.get(key)

                if raw is None:
                    continue

                try:
                    if isinstance(raw, (int, float, str)):
                        value = float(raw)
                        break

                    if isinstance(raw, dict):
                        for subkey in subkeys:
                            if raw.get(subkey) is not None:
                                value = float(raw.get(subkey))
                                break

                        if value is not None:
                            break

                except Exception:
                    continue

            if value is None and isinstance(data.get("data"), dict):
                nested = data.get("data")

                for key in keys:
                    raw = nested.get(key)

                    if raw is None:
                        continue

                    try:
                        if isinstance(raw, (int, float, str)):
                            value = float(raw)
                            break

                        if isinstance(raw, dict):
                            for subkey in subkeys:
                                if raw.get(subkey) is not None:
                                    value = float(raw.get(subkey))
                                    break

                            if value is not None:
                                break

                    except Exception:
                        continue

        if value is None:
            return {
                "available": False,
                "value": None,
                "state": "⚪ unavailable",
                "reason": "cbbi_parse_failed",
                "source": "colintalkscrypto",
                "raw_keys": list(data.keys()) if isinstance(data, dict) else None,
            }

        if value >= 85:
            state = "🔴 cycle_top_risk"
        elif value >= 75:
            state = "🟠 late_cycle"
        elif value >= 55:
            state = "🟡 mid_cycle"
        elif value >= 30:
            state = "🟢 early_mid_cycle"
        else:
            state = "🟢 accumulation_zone"

        return {
            "available": True,
            "value": round(value, 2),
            "state": state,
            "reason": "ok",
            "source": "colintalkscrypto",
        }

    except Exception as e:
        return {
            "available": False,
            "value": None,
            "state": "⚪ unavailable",
            "reason": f"cbbi_parse_error:{e}",
            "source": "colintalkscrypto",
        }


def build_cycle_score(pi_cycle, cbbi):
    score = 0
    reasons = []

    if pi_cycle.get("top_risk"):
        score -= 30
        reasons.append("pi_cycle_top_risk")
    elif pi_cycle.get("status") == "late_cycle":
        score -= 15
        reasons.append("pi_cycle_late_cycle")
    elif pi_cycle.get("status") == "mid_late_cycle":
        score -= 5
        reasons.append("pi_cycle_mid_late")

    cbbi_value = cbbi.get("value") if isinstance(cbbi, dict) else None

    if cbbi_value is not None:
        if cbbi_value >= 85:
            score -= 30
            reasons.append("cbbi_cycle_top_risk")
        elif cbbi_value >= 75:
            score -= 15
            reasons.append("cbbi_late_cycle")
        elif cbbi_value <= 30:
            score += 10
            reasons.append("cbbi_accumulation_zone")
    else:
        reasons.append("cbbi_missing")

    if score <= -45:
        state = "🔴 TOP_RISK"
    elif score <= -20:
        state = "🟠 LATE_CYCLE"
    elif score < 10:
        state = "🟡 NEUTRAL_CYCLE"
    else:
        state = "🟢 ACCUMULATION_SUPPORT"

    return {
        "cycle_score": score,
        "cycle_state": state,
        "reasons": reasons,
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

    data = await get_json(
        "https://open-api-v4.coinglass.com/api/futures/funding-rate/oi-weight-history",
        {"symbol": symbol},
        {"CG-API-KEY": COINGLASS_API_KEY},
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
        value = None

        if isinstance(last, list):
            value = float(last[-1])

        elif isinstance(last, dict):
            for key in ["close", "fundingRate", "funding_rate", "rate", "value"]:
                if last.get(key) is not None:
                    value = float(last.get(key))
                    break

        return {
            "available": value is not None,
            "reason": "ok" if value is not None else "parse_failed",
            "value": value,
            "source": "coinglass"
        }

    except Exception as e:
        return {
            "available": False,
            "reason": f"parse_error:{e}",
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

    data = await get_json(
        "https://open-api-v4.coinglass.com/api/futures/openInterest/ohlc-history",
        {
            "symbol": symbol,
            "interval": "1d",
            "limit": "2"
        },
        {"CG-API-KEY": COINGLASS_API_KEY},
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

        def extract(row):
            if isinstance(row, list):
                return float(row[-1])

            if isinstance(row, dict):
                for key in ["close", "openInterest", "open_interest", "oi", "value"]:
                    if row.get(key) is not None:
                        return float(row.get(key))

            return None

        current = extract(rows[-1])
        previous = extract(rows[-2])

        if current is None or previous in [None, 0]:
            return {
                "available": False,
                "reason": "oi_parse_failed",
                "value": None,
                "change_24h_pct": None,
                "source": "coinglass"
            }

        return {
            "available": True,
            "reason": "ok",
            "value": current,
            "change_24h_pct": round(((current - previous) / previous) * 100, 2),
            "source": "coinglass",
        }

    except Exception as e:
        return {
            "available": False,
            "reason": f"parse_error:{e}",
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
        ctxs = data[1]
        universe = meta.get("universe", [])
        result = {}

        for i, asset in enumerate(universe):
            name = asset.get("name")
            if name:
                result[name.upper()] = ctxs[i] if i < len(ctxs) else {}

        return result

    except Exception as e:
        print(f"HYPERLIQUID PARSE ERROR: {e}")
        return {}


def get_hyperliquid_derivatives(symbol, contexts):
    hl = HYPERLIQUID_SYMBOLS.get(symbol)
    ctx = contexts.get(hl.upper()) if hl else None

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
            },
        }

    try:
        funding = float(ctx.get("funding")) if ctx.get("funding") is not None else None
    except Exception:
        funding = None

    try:
        oi = float(ctx.get("openInterest")) if ctx.get("openInterest") is not None else None
    except Exception:
        oi = None

    return {
        "funding": {
            "available": funding is not None,
            "reason": "ok" if funding is not None else "funding_missing",
            "value": funding,
            "source": "hyperliquid"
        },
        "open_interest": {
            "available": oi is not None,
            "reason": "ok" if oi is not None else "oi_missing",
            "value": oi,
            "change_24h_pct": None,
            "source": "hyperliquid"
        },
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
    cbbi = await get_cbbi()
    cycle_intelligence = build_cycle_score(pi_cycle, cbbi)
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

        funding = await get_coinglass_funding(DERIVATIVE_SYMBOLS.get(symbol))
        open_interest = await get_coinglass_open_interest(DERIVATIVE_SYMBOLS.get(symbol))
        source_priority = "coinglass"

        if not funding.get("available") or not open_interest.get("available"):
            fallback = get_hyperliquid_derivatives(symbol, hyperliquid_contexts)

            if not funding.get("available") and fallback["funding"].get("available"):
                funding = fallback["funding"]
                source_priority = "hyperliquid_fallback"

            if not open_interest.get("available") and fallback["open_interest"].get("available"):
                open_interest = fallback["open_interest"]
                source_priority = "hyperliquid_fallback"

        atr = synthetic_atr(price, change_24h)

        coins[symbol] = {
            **base,
            "rsi_14d": synthetic_rsi(change_24h),
            "atr_14d": atr,
            "volatility": classify_volatility(price, atr),
            "trend": classify_trend(change_24h),
            "indicator_method": "synthetic_proxy_model",
            "derivatives": {
                "source_priority": source_priority,
                "funding": funding,
                "open_interest": open_interest,
                "state": classify_derivatives(funding, open_interest),
            },
        }

    altseason_index = round(max(0, 100 - btc_dominance), 2) if btc_dominance is not None else None
    stablecoin_regime = "🟡 neutral"

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
        "cbbi_enabled": cbbi.get("available"),
        "coins": coins,
        "btc": {
            "dominance": btc_dominance,
            "fear_greed": fear_greed,
            "altseason_index": altseason_index,
            "stablecoin_regime": stablecoin_regime,
            "cbbi": cbbi,
            "pi_cycle": pi_cycle,
            "cycle_intelligence": cycle_intelligence,
        },
        "missing_data": [] if cbbi.get("available") else ["cbbi_live_parse_or_endpoint"],
    }

    CACHE["snapshot"] = snapshot
    CACHE["timestamp"] = time.time()

    return snapshot
