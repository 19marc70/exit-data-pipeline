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

BYBIT_SYMBOLS = {
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
            response = await client.get(url, params=params)

            if response.status_code == 429:
                print(f"RATE LIMIT HIT: {url}")
                return None

            response.raise_for_status()
            return response.json()

    except Exception as e:
        print(f"HTTP ERROR: {url} -> {e}")
        return None


def calculate_rsi(closes, period=14):
    if len(closes) < period + 1:
        return None

    gains = []
    losses = []

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


async def get_bybit_klines(symbol):
    try:
        data = await get_json(
            "https://api.bybit.com/v5/market/kline",
            {
                "category": "linear",
                "symbol": symbol,
                "interval": "D",
                "limit": 30
            }
        )

        if not data:
            print(f"BYBIT ERROR: no data for {symbol}")
            return None

        result = data.get("result", {})
        klines = result.get("list", [])

        if not klines:
            print(f"BYBIT EMPTY: {symbol}")
            return None

        print(f"BYBIT SUCCESS: {symbol}")

        # Bybit geeft nieuwste candle eerst; omkeren naar oud → nieuw
        return list(reversed(klines))

    except Exception as e:
        print(f"BYBIT EXCEPTION {symbol}: {e}")
        return None


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

        rsi = None
        atr = None
        volatility = "⚪ unavailable"
        indicator_method = "unavailable"

        bybit_symbol = BYBIT_SYMBOLS.get(symbol)

        if bybit_symbol:
            klines = await get_bybit_klines(bybit_symbol)

            if klines:
                try:
                    closes = [float(k[4]) for k in klines]

                    rsi = calculate_rsi(closes)
                    atr = calculate_atr(klines)
                    volatility = classify_volatility(price, atr)
                    indicator_method = "bybit_1d_klines"

                except Exception as e:
                    print(f"INDICATOR ERROR {symbol}: {e}")

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
