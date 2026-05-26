import os
import time
import asyncio
import httpx
from datetime import datetime, timezone

from .indicators import build_coin_indicators, build_btc_pi_cycle


CACHE = {
    "snapshot": None,
    "timestamp": 0
}

CACHE_TTL_SECONDS = int(os.getenv("CACHE_TTL_SECONDS", "900"))
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

HOLDINGS = {
    "XRP": float(os.getenv("HOLDING_XRP", "11093.5")),
    "ONDO": float(os.getenv("HOLDING_ONDO", "22397.63463725")),
    "AERO": float(os.getenv("HOLDING_AERO", "10251.39604089")),
    "CFG": float(os.getenv("HOLDING_CFG", "10667.05368724")),
}

AVG_ENTRY = {
    "XRP": float(os.getenv("AVG_ENTRY_XRP", "0.9699")),
    "ONDO": float(os.getenv("AVG_ENTRY_ONDO", "0.5018")),
    "AERO": float(os.getenv("AVG_ENTRY_AERO", "0.5379")),
    "CFG": float(os.getenv("AVG_ENTRY_CFG", "0.2268")),
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


def extract_latest_numeric(raw):
    if raw is None:
        return None

    if isinstance(raw, (int, float)):
        return float(raw)

    if isinstance(raw, str):
        try:
            return float(raw)
        except Exception:
            return None

    if isinstance(raw, list):
        nums = []
        for item in raw:
            val = extract_latest_numeric(item)
            if val is not None:
                nums.append(val)
        return nums[-1] if nums else None

    if isinstance(raw, dict):
        preferred = [
            "value",
            "current",
            "score",
            "confidence",
            "Confidence",
            "latest",
            "last"
        ]

        for key in preferred:
            if raw.get(key) is not None:
                val = extract_latest_numeric(raw.get(key))
                if val is not None:
                    return val

        nums = []
        for _, v in raw.items():
            val = extract_latest_numeric(v)
            if val is not None:
                nums.append(val)

        return nums[-1] if nums else None

    return None


async def get_cbbi_bundle():
    data = await get_json("https://colintalkscrypto.com/cbbi/data/latest.json")

    if not data:
        return {
            "available": False,
            "source": "colintalkscrypto",
            "reason": "cbbi_endpoint_unavailable",
            "raw_keys": None,
            "cbbi": {
                "available": False,
                "value": None,
                "state": "⚪ unavailable"
            },
            "macro_components": {}
        }

    raw_keys = list(data.keys()) if isinstance(data, dict) else None

    def get_component(name):
        raw = data.get(name) if isinstance(data, dict) else None
        value = extract_latest_numeric(raw)

        return {
            "available": value is not None,
            "value": round(value, 4) if value is not None else None,
            "source_key": name
        }

    confidence_value = extract_latest_numeric(data.get("Confidence")) if isinstance(data, dict) else None

    if confidence_value is None:
        for key in ["CBBI", "cbbi", "value", "index"]:
            if isinstance(data, dict):
                confidence_value = extract_latest_numeric(data.get(key))
                if confidence_value is not None:
                    break

    if confidence_value is None:
        cbbi = {
            "available": False,
            "value": None,
            "state": "⚪ unavailable",
            "reason": "cbbi_parse_failed",
            "source": "colintalkscrypto",
            "raw_keys": raw_keys
        }
    else:
        if confidence_value >= 85:
            state = "🔴 cycle_top_risk"
        elif confidence_value >= 75:
            state = "🟠 late_cycle"
        elif confidence_value >= 55:
            state = "🟡 mid_cycle"
        elif confidence_value >= 30:
            state = "🟢 early_mid_cycle"
        else:
            state = "🟢 accumulation_zone"

        cbbi = {
            "available": True,
            "value": round(confidence_value, 2),
            "state": state,
            "reason": "ok",
            "source": "colintalkscrypto"
        }

    macro_components = {
        "mvrv": get_component("MVRV"),
        "puell": get_component("Puell"),
        "reserve_risk": get_component("ReserveRisk"),
        "rupl": get_component("RUPL"),
        "rhodl": get_component("RHODL"),
        "two_year_ma": get_component("2YMA"),
        "pi_cycle_raw": get_component("PiCycle")
    }

    return {
        "available": cbbi.get("available"),
        "source": "colintalkscrypto",
        "reason": "ok" if cbbi.get("available") else "cbbi_unavailable",
        "raw_keys": raw_keys,
        "cbbi": cbbi,
        "macro_components": macro_components
    }


def classify_macro_component(name, value):
    if value is None:
        return {
            "score": 0,
            "state": "⚪ unavailable",
            "reason": f"{name}_missing"
        }

    score = 0
    state = "🟡 neutral"
    reason = f"{name}_neutral"

    if name == "mvrv":
        if value >= 3.5:
            score = -20
            state = "🔴 overvaluation_risk"
            reason = "mvrv_extreme"
        elif value >= 2.5:
            score = -10
            state = "🟠 elevated"
            reason = "mvrv_elevated"
        elif value <= 1.0:
            score = 10
            state = "🟢 undervalued"
            reason = "mvrv_accumulation"

    elif name == "puell":
        if value >= 4:
            score = -15
            state = "🔴 miner_overheat"
            reason = "puell_extreme"
        elif value >= 2.5:
            score = -8
            state = "🟠 elevated"
            reason = "puell_elevated"
        elif value <= 0.6:
            score = 8
            state = "🟢 miner_capitulation_zone"
            reason = "puell_accumulation"

    elif name == "reserve_risk":
        if value >= 0.02:
            score = -15
            state = "🔴 long_term_holder_risk"
            reason = "reserve_risk_high"
        elif value >= 0.01:
            score = -8
            state = "🟠 elevated"
            reason = "reserve_risk_elevated"
        elif value <= 0.002:
            score = 8
            state = "🟢 conviction_discount"
            reason = "reserve_risk_low"

    elif name == "rupl":
        if value >= 0.75:
            score = -15
            state = "🔴 unrealized_profit_extreme"
            reason = "rupl_extreme"
        elif value >= 0.55:
            score = -8
            state = "🟠 elevated_profit"
            reason = "rupl_elevated"
        elif value <= 0.25:
            score = 8
            state = "🟢 low_unrealized_profit"
            reason = "rupl_accumulation"

    elif name == "rhodl":
        if value >= 50000:
            score = -15
            state = "🔴 cycle_heat"
            reason = "rhodl_extreme"
        elif value >= 25000:
            score = -8
            state = "🟠 elevated"
            reason = "rhodl_elevated"
        elif value <= 5000:
            score = 8
            state = "🟢 accumulation_zone"
            reason = "rhodl_low"

    return {
        "score": score,
        "state": state,
        "reason": reason
    }


def build_macro_intelligence(macro_components):
    score = 0
    signals = {}
    reasons = []

    for name, component in macro_components.items():
        value = component.get("value") if isinstance(component, dict) else None
        classification = classify_macro_component(name, value)

        signals[name] = {
            "available": component.get("available") if isinstance(component, dict) else False,
            "value": value,
            "state": classification["state"],
            "score": classification["score"],
            "reason": classification["reason"]
        }

        score += classification["score"]

        if classification["reason"] and not classification["reason"].endswith("_missing"):
            reasons.append(classification["reason"])

    if score <= -40:
        state = "🔴 MACRO_TOP_RISK"
    elif score <= -20:
        state = "🟠 MACRO_LATE_CYCLE"
    elif score < 10:
        state = "🟡 MACRO_NEUTRAL"
    else:
        state = "🟢 MACRO_ACCUMULATION_SUPPORT"

    return {
        "macro_score": score,
        "macro_state": state,
        "signals": signals,
        "reasons": reasons
    }


def build_cycle_score(pi_cycle, cbbi, macro_intelligence):
    score = 0
    reasons = []

    if pi_cycle.get("top_risk") or pi_cycle.get("triggered"):
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

    macro_score = macro_intelligence.get("macro_score", 0)
    score += macro_score

    for reason in macro_intelligence.get("reasons", []):
        reasons.append(reason)

    if score <= -60:
        state = "🔴 FULL_CYCLE_TOP_RISK"
    elif score <= -30:
        state = "🟠 LATE_CYCLE_RISK"
    elif score < 15:
        state = "🟡 NEUTRAL_CYCLE"
    else:
        state = "🟢 ACCUMULATION_SUPPORT"

    return {
        "cycle_score": score,
        "cycle_state": state,
        "reasons": reasons,
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


async def build_derivatives(symbol, hyperliquid_contexts):
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

    return {
        "source_priority": source_priority,
        "funding": funding,
        "open_interest": open_interest,
        "state": classify_derivatives(funding, open_interest),
    }


async def build_exit_snapshot():
    if cache_valid():
        cached = CACHE["snapshot"].copy()
        cached["cache_mode"] = "fresh_cache"
        return cached

prices, btc_dominance, fear_greed, cbbi_bundle, pi_cycle, hyperliquid_contexts = await asyncio.gather(
    get_prices(),
    get_btc_dominance(),
    get_fear_greed(),
    get_cbbi_bundle(),
    build_btc_pi_cycle(),
    get_hyperliquid_contexts(),
)

    cbbi = cbbi_bundle.get("cbbi", {})
    macro_components = cbbi_bundle.get("macro_components", {})


    
    macro_intelligence = build_macro_intelligence(macro_components)
    cycle_intelligence = build_cycle_score(pi_cycle, cbbi, macro_intelligence)
    if not prices:
        fallback = CACHE["snapshot"] or {
            "timestamp": now_iso(),
            "status": "degraded",
            "coins": {},
            "btc": {},
            "missing_data": ["coingecko_unavailable"]
        }
        fallback["timestamp"] = now_iso()
        fallback["status"] = "degraded"
        fallback["cache_mode"] = "fallback_cache_active"
        fallback["api_error"] = "coingecko_unavailable"
        return fallback

    symbols = list(COINS.keys())

    indicator_results = await asyncio.gather(
        *[build_coin_indicators(symbol) for symbol in symbols],
        return_exceptions=True
    )

    derivative_results = await asyncio.gather(
        *[build_derivatives(symbol, hyperliquid_contexts) for symbol in symbols],
        return_exceptions=True
    )

    coins = {}
    coin_indicators = {}
    missing_data = []

    for symbol, indicator_result, derivative_result in zip(symbols, indicator_results, derivative_results):
        coin_id = COINS[symbol]
        base = prices.get(coin_id, {}) or {}

        price = base.get("usd")
        change_24h = base.get("usd_24h_change")

        if isinstance(indicator_result, Exception):
            missing_data.append(f"{symbol}_indicator_error")
            indicator = {
                "symbol": symbol,
                "current_price": price,
                "rsi_14d": None,
                "atr_14d": None,
                "atr_pct_14d": None,
                "volatility": "⚪ unavailable",
                "indicator_method": "indicator_error",
                "error": str(indicator_result),
            }
        else:
            indicator = indicator_result

        if isinstance(derivative_result, Exception):
            missing_data.append(f"{symbol}_derivatives_error")
            derivatives = {
                "source_priority": "unavailable",
                "funding": {"available": False, "reason": "error", "value": None},
                "open_interest": {"available": False, "reason": "error", "value": None},
                "state": {"leverage_risk": "⚪ unknown", "reasons": ["derivatives_error"]},
            }
        else:
            derivatives = derivative_result

        trend = classify_trend(change_24h)

        coin = {
            **base,
            "current_price": indicator.get("current_price") or price,
            "rsi_14d": indicator.get("rsi_14d"),
            "atr_14d": indicator.get("atr_14d"),
            "atr_pct_14d": indicator.get("atr_pct_14d"),
            "volatility": indicator.get("volatility"),
            "trend": trend,
            "indicator_method": indicator.get("indicator_method", "daily_ohlc_rsi_atr"),
            "timeframe": indicator.get("timeframe", "1d"),
            "candles_used": indicator.get("candles_used"),
            "liquidity": "🟢 strong" if base.get("usd_24h_vol", 0) >= 5_000_000 else "🔴 severe",
            "derivatives": derivatives,
        }

        coins[symbol] = coin
        coin_indicators[symbol] = coin

    altseason_index = round(max(0, 100 - btc_dominance), 2) if btc_dominance is not None else None
    stablecoin_regime = "🟡 neutral"

    if fear_greed.get("value") is not None:
        fg = fear_greed["value"]

        if fg <= 25:
            stablecoin_regime = "🟢 defensive_rotation"
        elif fg >= 75:
            stablecoin_regime = "🔴 euphoric_risk"

    if not cbbi.get("available"):
        missing_data.append("cbbi_live_parse_or_endpoint")

    for name, item in macro_components.items():
        if not item.get("available"):
            missing_data.append(f"{name}_macro_component")

    snapshot = {
        "timestamp": now_iso(),
        "status": "ok",
        "source": "exit-data-pipeline",
        "cache_mode": "live",
        "cache_ttl_seconds": CACHE_TTL_SECONDS,
        "coinglass_enabled": bool(COINGLASS_API_KEY),
        "hyperliquid_fallback_enabled": True,
        "cycle_intelligence_enabled": True,
        "macro_intelligence_enabled": True,
        "cbbi_enabled": cbbi.get("available"),
        "holdings": HOLDINGS,
        "avg_entry": AVG_ENTRY,
        "coins": coins,
        "coin_indicators": coin_indicators,
        "pi_cycle": pi_cycle,
        "btc": {
            "dominance": btc_dominance,
            "fear_greed": fear_greed,
            "altseason_index": altseason_index,
            "stablecoin_regime": stablecoin_regime,
            "cbbi": cbbi,
            "macro_components": macro_components,
            "macro_intelligence": macro_intelligence,
            "pi_cycle": pi_cycle,
            "cycle_intelligence": cycle_intelligence,
        },
        "missing_data": missing_data,
    }

    CACHE["snapshot"] = snapshot
    CACHE["timestamp"] = time.time()

    return snapshot
