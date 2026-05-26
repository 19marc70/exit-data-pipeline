import math
import asyncio
import httpx
import pandas as pd
from functools import lru_cache


COINGECKO_IDS = {
    "BTC": "bitcoin",
    "XRP": "ripple",
    "ONDO": "ondo-finance",
    "AERO": "aerodrome-finance",
    "CFG": "centrifuge",
}


@lru_cache(maxsize=20)
def get_coin_id(symbol):
    return COINGECKO_IDS[symbol.upper()]


async def fetch_market_chart(symbol, days=90):
    coin_id = get_coin_id(symbol)

    url = f"https://api.coingecko.com/api/v3/coins/{coin_id}/market_chart"

    params = {
        "vs_currency": "usd",
        "days": str(days),
        "interval": "daily",
    }

    async with httpx.AsyncClient(timeout=30) as client:
        response = await client.get(url, params=params)

        if response.status_code == 429:
            await asyncio.sleep(15)
            response = await client.get(url, params=params)

        response.raise_for_status()
        return response.json()


async def get_daily_ohlc(symbol, days=90):
    data = await fetch_market_chart(symbol, days)
    prices = data.get("prices", [])

    if len(prices) < 30:
        raise Exception(f"Not enough candles for {symbol}")

    df = pd.DataFrame(prices, columns=["timestamp", "close"])

    df["timestamp"] = pd.to_datetime(df["timestamp"], unit="ms")
    df["close"] = pd.to_numeric(df["close"], errors="coerce")

    df["open"] = df["close"].shift(1)
    df["open"] = df["open"].fillna(df["close"])

    df["high"] = df[["open", "close"]].max(axis=1)
    df["low"] = df[["open", "close"]].min(axis=1)

    return df.dropna().reset_index(drop=True)


def calculate_rsi(close, period=14):
    if close is None or len(close) < period + 10:
        return None

    delta = close.diff()

    gain = delta.clip(lower=0)
    loss = -delta.clip(upper=0)

    avg_gain = gain.ewm(alpha=1 / period, adjust=False).mean()
    avg_loss = loss.ewm(alpha=1 / period, adjust=False).mean()

    rs = avg_gain / avg_loss.replace(0, math.nan)
    rsi = 100 - (100 / (1 + rs))

    value = rsi.iloc[-1]

    if pd.isna(value):
        return None

    return round(float(value), 2)


def calculate_atr(df, period=14):
    if df is None or len(df) < period + 10:
        return {
            "atr_14d": None,
            "atr_pct_14d": None,
            "volatility": "⚪ insufficient_data",
        }

    high = df["high"]
    low = df["low"]
    close = df["close"]

    prev_close = close.shift()

    tr = pd.concat(
        [
            high - low,
            (high - prev_close).abs(),
            (low - prev_close).abs(),
        ],
        axis=1,
    ).max(axis=1)

    atr = tr.ewm(alpha=1 / period, adjust=False).mean().iloc[-1]
    price = close.iloc[-1]

    if price <= 0 or pd.isna(atr):
        return {
            "atr_14d": None,
            "atr_pct_14d": None,
            "volatility": "⚪ unavailable",
        }

    atr_pct = (atr / price) * 100

    if atr_pct < 2:
        volatility = "🟢 low"
    elif atr_pct < 5:
        volatility = "🟡 medium"
    elif atr_pct < 8:
        volatility = "🟠 elevated"
    else:
        volatility = "🔴 high"

    return {
        "atr_14d": round(float(atr), 6),
        "atr_pct_14d": round(float(atr_pct), 2),
        "volatility": volatility,
    }


async def build_coin_indicators(symbol):
    try:
        df = await get_daily_ohlc(symbol, 90)
        atr = calculate_atr(df)
        rsi = calculate_rsi(df["close"])

        return {
            "symbol": symbol.upper(),
            "timeframe": "1d",
            "candles_used": len(df),
            "current_price": round(float(df["close"].iloc[-1]), 6),
            "rsi_14d": rsi,
            "atr_14d": atr["atr_14d"],
            "atr_pct_14d": atr["atr_pct_14d"],
            "volatility": atr["volatility"],
            "indicator_method": "coingecko_cached_retry_v3",
        }

    except Exception as e:
        return {
            "symbol": symbol.upper(),
            "timeframe": "1d",
            "candles_used": None,
            "current_price": None,
            "rsi_14d": None,
            "atr_14d": None,
            "atr_pct_14d": None,
            "volatility": "⚪ unavailable",
            "indicator_method": "indicator_error",
            "error": str(e),
        }


async def build_btc_pi_cycle():
    try:
        df = await get_daily_ohlc("BTC", 365)

        if df is None or len(df) < 350:
            return {
                "status": "unknown",
                "cycle_state": "⚪ insufficient_history",
                "ma_111": None,
                "ma_350x2": None,
                "distance_pct": None,
                "top_risk": False,
                "triggered": False,
                "method": "pi_cycle_111dma_vs_350dma_x2",
            }

        close = df["close"]

        ma111 = close.rolling(111).mean().iloc[-1]
        ma350x2 = close.rolling(350).mean().iloc[-1] * 2

        distance_pct = ((ma350x2 - ma111) / ma111) * 100

        if ma111 >= ma350x2:
            status = "top_risk"
            state = "🔴 TOP_RISK"
            top_risk = True
            triggered = True
        elif distance_pct <= 10:
            status = "late_cycle"
            state = "🟠 LATE_CYCLE"
            top_risk = False
            triggered = False
        elif distance_pct <= 25:
            status = "mid_late_cycle"
            state = "🟡 MID_LATE_CYCLE"
            top_risk = False
            triggered = False
        else:
            status = "early_mid_cycle"
            state = "🟢 EARLY_MID_CYCLE"
            top_risk = False
            triggered = False

        return {
            "status": status,
            "cycle_state": state,
            "ma_111": round(float(ma111), 2),
            "ma_350x2": round(float(ma350x2), 2),
            "distance_pct": round(float(distance_pct), 2),
            "top_risk": top_risk,
            "triggered": triggered,
            "method": "pi_cycle_111dma_vs_350dma_x2",
        }

    except Exception as e:
        return {
            "status": "unknown",
            "cycle_state": "⚪ unavailable",
            "ma_111": None,
            "ma_350x2": None,
            "distance_pct": None,
            "top_risk": False,
            "triggered": False,
            "method": "pi_cycle_111dma_vs_350dma_x2",
            "error": str(e),
        }
