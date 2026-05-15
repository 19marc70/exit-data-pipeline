import os
import httpx
import statistics

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


async def fetch_coin_prices():
    ids = ",".join(COINS.values())

    url = (
        "https://api.coingecko.com/api/v3/simple/price"
        f"?ids={ids}"
        "&vs_currencies=usd"
        "&include_market_cap=true"
        "&include_24hr_vol=true"
        "&include_24hr_change=true"
    )

    async with httpx.AsyncClient(timeout=20) as client:
        response = await client.get(url)

        if response.status_code != 200:
            return None

        return response.json()


async def fetch_binance_klines(symbol: str):
    url = (
        "https://api.binance.com/api/v3/klines"
        f"?symbol={symbol}"
        "&interval=1d"
        "&limit=30"
    )

    async with httpx.AsyncClient(timeout=20) as client:
        response = await client.get(url)

        if response.status_code != 200:
            return None

        return response.json()


def calculate_rsi(closes, period=14):
    if len(closes) < period + 1:
        return None

    gains = []
    losses = []

    for i in range(1, len(closes)):
        diff = closes[i] - closes[i - 1]

        if diff >= 0:
            gains.append(diff)
            losses.append(0)
        else:
            gains.append(0)
            losses.append(abs(diff))

    avg_gain = sum(gains[:period]) / period
    avg_loss = sum(losses[:period]) / period

    if avg_loss == 0:
        return 100

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

    return round(sum(trs[:period]) / period, 4)


def classify_volatility(atr, price):
    if atr is None or price <= 0:
        return "⚪ unavailable"

    ratio = atr / price

    if ratio < 0.02:
        return "🟢 low"

    if ratio < 0.05:
        return "🟡 medium"

    return "🔴 high"


def classify_trend(change_24h):
    if change_24h >= 3:
        return "🟢 strengthening"

    if change_24h <= -3:
        return "🟠 weakening"

    return "🟡 sideways"


async def get_market_snapshot():

    prices = await fetch_coin_prices()

    if not prices:
        return {
            "status": "degraded",
            "missing_data": ["live_market_data"]
        }

    coins = {}

    for ticker, cg_id in COINS.items():

        coin = prices.get(cg_id, {})

        price = coin.get("usd")
        volume = coin.get("usd_24h_vol", 0)
        change_24h = coin.get("usd_24h_change", 0)
        market_cap = coin.get("usd_market_cap", 0)

        rsi = None
        atr = None
        volatility = "⚪ unavailable"

        symbol = BINANCE_SYMBOLS.get(ticker)

        if symbol:

            klines = await fetch_binance_klines(symbol)

            if klines:

                closes = [float(k[4]) for k in klines]

                rsi = calculate_rsi(closes)

                atr = calculate_atr(klines)

                if atr and price:
                    volatility = classify_volatility(atr, price)

        coins[ticker] = {
            "usd": price,
            "usd_market_cap": market_cap,
            "usd_24h_vol": volume,
            "usd_24h_change": change_24h,
            "rsi_14d": rsi,
            "atr_14d": atr,
            "volatility": volatility,
            "trend": classify_trend(change_24h)
        }

    return {
        "timestamp": "live",
        "status": "ok",
        "cache_ttl_seconds": CACHE_TTL_SECONDS,
        "coins": coins
    }
