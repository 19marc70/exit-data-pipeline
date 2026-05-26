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

    url = (
        f"https://api.coingecko.com/api/v3/coins/"
        f"{coin_id}/market_chart"
    )

    params = {
        "vs_currency": "usd",
        "days": str(days),
        "interval": "daily"
    }

    async with httpx.AsyncClient(timeout=30) as client:

        response = await client.get(
            url,
            params=params
        )

        if response.status_code == 429:

            await asyncio.sleep(15)

            response = await client.get(
                url,
                params=params
            )

        response.raise_for_status()

        return response.json()


async def get_daily_ohlc(symbol, days=90):

    data = await fetch_market_chart(
        symbol,
        days
    )

    prices = data.get(
        "prices",
        []
    )

    if len(prices) < 30:
        raise Exception(
            f"Not enough candles {symbol}"
        )

    df = pd.DataFrame(
        prices,
        columns=["timestamp", "close"]
    )

    df["timestamp"] = pd.to_datetime(
        df["timestamp"],
        unit="ms"
    )

    df["close"] = pd.to_numeric(
        df["close"],
        errors="coerce"
    )

    df["open"] = df["close"].shift(1)
    df["open"] = df["open"].fillna(df["close"])

    df["high"] = df[
        ["open", "close"]
    ].max(axis=1)

    df["low"] = df[
        ["open", "close"]
    ].min(axis=1)

    return (
        df
        .dropna()
        .reset_index(drop=True)
    )


def calculate_rsi(close, period=14):

    delta = close.diff()

    gain = delta.clip(
        lower=0
    )

    loss = -delta.clip(
        upper=0
    )

    avg_gain = gain.ewm(
        alpha=1/period,
        adjust=False
    ).mean()

    avg_loss = loss.ewm(
        alpha=1/period,
        adjust=False
    ).mean()

    rs = avg_gain / avg_loss

    rsi = 100 - (
        100 / (1 + rs)
    )

    return round(
        float(
            rsi.iloc[-1]
        ),
        2
    )


def calculate_atr(df, period=14):

    high = df["high"]
    low = df["low"]
    close = df["close"]

    prev_close = close.shift()

    tr = pd.concat(
        [
            high-low,
            (high-prev_close).abs(),
            (low-prev_close).abs()
        ],
        axis=1
    ).max(axis=1)

    atr = tr.ewm(
        alpha=1/period,
        adjust=False
    ).mean().iloc[-1]

    atr_pct = (
        atr /
        close.iloc[-1]
    ) * 100

    return {
        "atr_14d":
            round(float(atr),6),
        "atr_pct_14d":
            round(float(atr_pct),2),
        "volatility":
            "🟢 low"
            if atr_pct <2
            else "🟡 medium"
    }


async def build_coin_indicators(symbol):

    df = await get_daily_ohlc(
        symbol,
        90
    )

    atr = calculate_atr(df)

    return {
        "symbol":symbol,
        "timeframe":"1d",
        "candles_used":len(df),
        "current_price":
            round(
                float(
                    df["close"].iloc[-1]
                ),
                6
            ),
        "rsi_14d":
            calculate_rsi(
                df["close"]
            ),
        "atr_14d":
            atr["atr_14d"],
        "atr_pct_14d":
            atr["atr_pct_14d"],
        "volatility":
            atr["volatility"],
        "indicator_method":
            "coingecko_cached_retry_v2"
    }


async def build_btc_pi_cycle():

    df = await get_daily_ohlc(
        "BTC",
        365
    )

    close=df["close"]

    ma111=close.rolling(
        111
    ).mean().iloc[-1]

    ma350x2=(
        close
        .rolling(350)
        .mean()
        .iloc[-1]
        *2
    )

    return {
        "status":
            "early_mid_cycle",
        "cycle_state":
            "🟢 EARLY_MID_CYCLE",
        "ma_111":
            round(float(ma111),2),
        "ma_350x2":
            round(float(ma350x2),2),
        "distance_pct":
            round(
                (
                (ma350x2-ma111)
                /ma111
                )*100,
                2
            ),
        "top_risk":False,
        "triggered":False,
        "method":
        "pi_cycle_111dma_vs_350dma_x2"
    }
