import math
import httpx
import pandas as pd


COINGECKO_IDS = {
    "BTC": "bitcoin",
    "XRP": "ripple",
    "ONDO": "ondo-finance",
    "AERO": "aerodrome-finance",
    "CFG": "centrifuge",
}


async def get_daily_ohlc(symbol: str, days: int = 365) -> pd.DataFrame:
    symbol = symbol.upper()
    coin_id = COINGECKO_IDS[symbol]

    url = f"https://api.coingecko.com/api/v3/coins/{coin_id}/ohlc"
    params = {"vs_currency": "usd", "days": "365"}

    async with httpx.AsyncClient(timeout=30) as client:
        response = await client.get(url, params=params)
        response.raise_for_status()
        data = response.json()

    df = pd.DataFrame(data, columns=["timestamp", "open", "high", "low", "close"])
    df["timestamp"] = pd.to_datetime(df["timestamp"], unit="ms", utc=True)
    df = df.sort_values("timestamp").drop_duplicates("timestamp")

    for col in ["open", "high", "low", "close"]:
        df[col] = pd.to_numeric(df[col], errors="coerce")

    return df.dropna().reset_index(drop=True)


def calculate_rsi(close: pd.Series, period: int = 14) -> float | None:
    close = close.dropna()

    if len(close) < period + 50:
        return None

    delta = close.diff()
    gain = delta.clip(lower=0)
    loss = -delta.clip(upper=0)

    avg_gain = gain.ewm(alpha=1 / period, adjust=False).mean()
    avg_loss = loss.ewm(alpha=1 / period, adjust=False).mean()

    rs = avg_gain / avg_loss.replace(0, math.nan)
    rsi = 100 - (100 / (1 + rs))

    value = rsi.iloc[-1]
    return round(float(value), 2) if pd.notna(value) else None


def calculate_atr(df: pd.DataFrame, period: int = 14) -> dict:
    if len(df) < period + 50:
        return {
            "atr_14d": None,
            "atr_pct_14d": None,
            "volatility": "⚪ insufficient_data",
        }

    high = df["high"]
    low = df["low"]
    close = df["close"]
    prev_close = close.shift(1)

    true_range = pd.concat(
        [
            high - low,
            (high - prev_close).abs(),
            (low - prev_close).abs(),
        ],
        axis=1,
    ).max(axis=1)

    atr = true_range.ewm(alpha=1 / period, adjust=False).mean().iloc[-1]
    price = close.iloc[-1]
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


def calculate_pi_cycle(df: pd.DataFrame) -> dict:
    if len(df) < 350:
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


async def build_coin_indicators(symbol: str) -> dict:
    df = await get_daily_ohlc(symbol)

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
        "indicator_method": "coingecko_daily_ohlc_wilder_rsi_atr",
    }


async def build_btc_pi_cycle() -> dict:
    df = await get_daily_ohlc("BTC")
    return calculate_pi_cycle(df)
