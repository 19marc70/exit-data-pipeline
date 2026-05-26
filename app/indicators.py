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
    symbol = symbol.upper()

    if symbol not in COINGECKO_IDS:
        raise ValueError(f"Unknown symbol: {symbol}")

    return COINGECKO_IDS[symbol]


async def fetch_market_chart(symbol, days=90):
    coin_id = get_coin_id(symbol)

    url = f"https://api.coingecko.com/api/v3/coins/{coin_id}/market_chart"

    params = {
        "vs_currency": "usd",
        "days": str(days),
        "interval": "daily",
    }

    async with httpx.AsyncClient(timeout=30) as client:
        for attempt in range(3):
            try:
                response = await client.get(url, params=params)

                if response.status_code == 429:
                    print(f"RATE LIMIT {symbol}")
                    await asyncio.sleep(10 * (attempt + 1))
                    continue

                response.raise_for_status()

                data = response.json()
                prices = data.get("prices", [])

                if len(prices) < 30:
                    raise Exception(f"Not enough prices for {symbol}: {len(prices)}")

                return data

            except Exception as e:
                print(f"FETCH ERROR {symbol}: {str(e)}")

                if attempt < 2:
                    await asyncio.sleep(5 * (attempt + 1))
                else:
                    raise e


async def get_daily_ohlc(symbol, days=90):
    data = await fetch_market_chart(symbol, days)
    prices = data.get("prices", [])

    df = pd.DataFrame(prices, columns=["timestamp", "close"])

    df["timestamp"] = pd.to_datetime(df["timestamp"], unit="ms", utc=True)
    df["close"] = pd.to_numeric(df["close"], errors="coerce")

    df = (
        df.dropna()
        .sort_values("timestamp")
        .drop_duplicates("timestamp")
        .reset_index(drop=True)
    )

    if len(df) < 30:
        raise Exception(f"Not enough clean candles for {symbol}: {len(df)}")

    df["open"] = df["close"].shift(1)
    df["open"] = df["open"].fillna(df["close"])

    df["high"] = df[["open", "close"]].max(axis=1)
    df["low"] = df[["open", "close"]].min(axis=1)

    return df


def calculate_rsi(close, period=14):
    if close is None or len(close) < period + 10:
        return None

    close = pd.to_numeric(close, errors="coerce").dropna()

    if len(close) < period + 10:
        return None

    delta = close.diff()

    gain = delta.clip(lower=0)
    loss = -delta.clip(upper=0)

    avg_gain = gain.ewm(alpha=1 / period, adjust=False).mean()
    avg_loss = loss.ewm(alpha=1 / period, adjust=False).mean()

    avg_loss = avg_loss.replace(0, math.nan)

    rs = avg_gain / avg_loss
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

    high = pd.to_numeric(df["high"], errors="coerce")
    low = pd.to_numeric(df["low"], errors="coerce")
    close = pd.to_numeric(df["close"], errors="coerce")

    prev_close = close.shift()

    tr = pd.concat(
        [
            high - low,
            (high - prev_close).abs(),
            (low - prev_close).abs(),
        ],
        axis=1,
    ).max(axis=1)

    atr_series = tr.ewm(alpha=1 / period, adjust=False).mean()

    atr = atr_series.iloc[-1]
    price = close.iloc[-1]

    if pd.isna(atr) or pd.isna(price) or price <= 0:
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
    symbol = symbol.upper()

    try:
        df = await get_daily_ohlc(symbol, 90)

        rsi = calculate_rsi(df["close"])
        atr = calculate_atr(df)

        return {
            "symbol": symbol,
            "timeframe": "1d",
            "candles_used": len(df),
            "current_price": round(float(df["close"].iloc[-1]), 6),
            "rsi_14d": rsi,
            "atr_14d": atr["atr_14d"],
            "atr_pct_14d": atr["atr_pct_14d"],
            "volatility": atr["volatility"],
            "indicator_method": "coingecko_market_chart_retry_v5",
        }

    except Exception as e:
        print(f"INDICATOR ERROR {symbol}: {str(e)}")

        return {
            "symbol": symbol,
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

        ma_111 = close.rolling(111).mean().iloc[-1]
        ma_350x2 = close.rolling(350).mean().iloc[-1] * 2

        if pd.isna(ma_111) or pd.isna(ma_350x2) or ma_111 <= 0:
            return {
                "status": "unknown",
                "cycle_state": "⚪ unavailable",
                "ma_111": None,
                "ma_350x2": None,
                "distance_pct": None,
                "top_risk": False,
                "triggered": False,
                "method": "pi_cycle_111dma_vs_350dma_x2",
            }

        distance_pct = ((ma_350x2 - ma_111) / ma_111) * 100

        if ma_111 >= ma_350x2:
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
            "ma_111": round(float(ma_111), 2),
            "ma_350x2": round(float(ma_350x2), 2),
            "distance_pct": round(float(distance_pct), 2),
            "top_risk": top_risk,
            "triggered": triggered,
            "method": "pi_cycle_111dma_vs_350dma_x2",
        }

    except Exception as e:
        print(f"PI CYCLE ERROR: {str(e)}")

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
