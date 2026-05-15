import os
import time
import httpx
from datetime import datetime, timezone

CACHE = {"snapshot": None, "timestamp": 0}
CACHE_TTL_SECONDS = int(os.getenv("CACHE_TTL_SECONDS", "7200"))

COINS = {
    "XRP": "ripple",
    "ONDO": "ondo-finance",
    "AERO": "aerodrome-finance",
    "CFG": "centrifuge"
}

BINANCE_SYMBOLS = {
    "XRP": "XRPUSDT",
    "ONDO": "ONDOUSDT",
    "AERO": "AEROUSDT",
    "CFG": "CFGUSDT"
}


def now_iso():
    return datetime.now(timezone.utc).isoformat()


def cache_valid():
    return CACHE["snapshot"] is not None and time.time() - CACHE["timestamp"] < CACHE_TTL_SECONDS


async def get_json(url, params=None):
    try:
        async with httpx.AsyncClient(timeout=25) as client:
            r = await client.get(url, params=params)
            if r.status_code == 429:
                return None
            r.raise_for_status()
            return r.json()
    except Exception:
        return None


def calculate_rsi(closes, period=14):
    if len(closes) < period + 1:
        return None

    gains, losses = [], []

    for i in range(1, len(closes)):
        diff = closes[i] - closes[i - 1]
        gains.append(max(diff, 0))
        losses.append(abs(min(diff, 0)))

    avg_gain = sum(gains[-period:]) / period
    avg_loss = sum(losses[-period:]) / period

    if avg_loss == 0:
        return 100.0

    rs = avg_gain / avg_loss
    return round(100 - (100 / (1 + rs)), 2)


def calculate_atr(klines, period=14):
    if len(klines) < period + 1:
        return None

    trs = []

    for i in range(1, len(klines)):
        high = float(klines[i][2])
        low = float(klines[i][3])
        prev_close = float(klines[i - 1][4])

        tr = max(
            high - low,
            abs(high - prev_close),
            abs(low - prev_close)
        )
        trs.append(tr)

    return round(sum(trs[-period:]) / period, 6)


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


def classify_trend(change_24h):
    if change_24h is None:
        return "⚪ unknown"
    if change_24h >= 3:
        return "🟢 strengthening"
    if change_24h <= -3:
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
            "include_24hr_change": "true"
        }
    )


async def get_binance_klines(symbol):
    return await get_json(
        "https://api.binance.com/api/v3/klines",
        {
            "symbol": symbol,
            "interval": "1d",
            "limit": 30
        }
    )


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
        cached = CACHE["snapshot"].copy()
        cached["cache_mode"] = "fresh_cache"
        return cached

    prices = await get_prices()
    btc_dominance = await get_btc_dominance()
    fear_greed = await get_fear_greed()

    if not prices and CACHE["snapshot"]:
        cached = CACHE["snapshot"].copy()
        cached["timestamp"] = now_iso()
        cached["status"] = "degraded"
        cached["cache_mode"] = "fallback_active"
        cached["api_error"] = "rate_limited_using_cached_data"
        return cached

    if not prices:
        return {
            "timestamp": now_iso(),
            "status": "degraded",
            "source": "exit-data-pipeline",
            "cache_mode": "no_cache_available",
            "api_error": "market_data_unavailable",
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
        price = base.get("usd")
        change_24h = base.get("usd_24h_change")
        binance_symbol = BINANCE_SYMBOLS.get(symbol)

        rsi = None
        atr = None
        volatility = "⚪ unavailable"
        indicator_method = "unavailable"

        klines = await get_binance_klines(binance_symbol) if binance_symbol else None

        if klines:
            closes = [float(k[4]) for k in klines]
            rsi = calculate_rsi(closes)
            atr = calculate_atr(klines)
            volatility = classify_volatility(price, atr)
            indicator_method = "binance_1d_klines"

        coins[symbol] = {
            **base,
            "rsi_14d": rsi,
            "atr_14d": atr,
            "volatility": volatility,
            "trend": classify_trend(change_24h),
            "indicator_method": indicator_method
        }

    altseason_index = None
    stablecoin_regime = None

    if btc_dominance is not None:
        altseason_index = round(max(0, 100 - btc_dominance), 2)

    if fear_greed and fear_greed.get("value") is not None:
        fg = fear_greed["value"]
        if fg <= 25:
            stablecoin_regime = "🟢 defensive_rotation"
        elif fg >= 75:
            stablecoin_regime = "🔴 euphoric_risk"
        else:
            stablecoin_regime = "🟡 neutral"

    snapshot = {
        "timestamp": now_iso(),
        "status": "ok",
        "source": "exit-data-pipeline",
        "cache_mode": "live",
        "cache_ttl_seconds": CACHE_TTL_SECONDS,
        "coins": coins,
        "raw_prices": prices,
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
            "pi_cycle",
            "funding_live",
            "open_interest_live"
        ]
    }

    CACHE["snapshot"] = snapshot
    CACHE["timestamp"] = time.time()

    return snapshot
