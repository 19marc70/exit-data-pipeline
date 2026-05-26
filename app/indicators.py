import math
import asyncio
import pandas as pd
import httpx
import ccxt.async_support as ccxt


LAST_GOOD_INDICATORS = {}
MARKET_CACHE = {}

SYMBOL_CANDIDATES = {
    "BTC": ["BTC/USDT", "BTC/USD"],
    "XRP": ["XRP/USDT", "XRP/USD"],
    "ONDO": ["ONDO/USDT", "ONDO/USD"],
    "AERO": ["AERO/USDT", "AERO/USD"],
    "CFG": ["CFG/USDT", "CFG/USD"],
}

EXCHANGES = [
    "binance",
    "bybit",
    "okx",
    "kucoin",
    "gateio",
    "bitget",
    "coinbase",
]


def create_exchange(name):
    exchange_class = getattr(ccxt, name)
    return exchange_class(
        {
            "enableRateLimit": True,
            "timeout": 30000,
        }
    )


async def load_markets(exchange):
    exchange_id = exchange.id

    if exchange_id in MARKET_CACHE:
        return MARKET_CACHE[exchange_id]

    markets = await exchange.load_markets()
    MARKET_CACHE[exchange_id] = markets

    return markets


async def fetch_ohlcv_from_exchange(exchange_name, symbol_candidates, timeframe="1d", limit=120):
    exchange = create_exchange(exchange_name)

    try:
        markets = await load_markets(exchange)

        for symbol in symbol_candidates:
            if symbol not in markets:
                continue

            candles = await exchange.fetch_ohlcv(
                symbol,
                timeframe=timeframe,
                limit=limit,
            )

            if candles and len(candles) >= 40:
                df = pd.DataFrame(
                    candles,
                    columns=["timestamp", "open", "high", "low", "close", "volume"],
                )

                df["timestamp"] = pd.to_datetime(df["timestamp"], unit="ms", utc=True)

                for col in ["open", "high", "low", "close", "volume"]:
                    df[col] = pd.to_numeric(df[col], errors="coerce")

                df = (
                    df.dropna()
                    .sort_values("timestamp")
                    .drop_duplicates("timestamp")
                    .reset_index(drop=True)
                )

                if len(df) >= 40:
                    return df, exchange_name, symbol

        return None, exchange_name, None

    finally:
        await exchange.close()


async def get_exchange_ohlcv(symbol, limit=120):
    symbol = symbol.upper()
    candidates = SYMBOL_CANDIDATES.get(symbol)

    if not candidates:
        raise ValueError(f"Unknown symbol: {symbol}")

    errors = []

    for exchange_name in EXCHANGES:
        try:
            df, source, used_symbol = await fetch_ohlcv_from_exchange(
                exchange_name,
                candidates,
                timeframe="1d",
                limit=limit,
            )

            if df is not None:
                return df, source, used_symbol

        except Exception as e:
            errors.append(f"{exchange_name}: {str(e)}")
            await asyncio.sleep(1)

    raise Exception(f"No OHLCV source found for {symbol}. Errors: {errors}")


def calculate_rsi(close, period=14):
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
        df, source, used_symbol = await get_exchange_ohlcv(
            symbol,
            limit=120,
        )

        rsi = calculate_rsi(df["close"])
        atr = calculate_atr(df)

        result = {
            "symbol": symbol,
            "timeframe": "1d",
            "candles_used": len(df),
            "current_price": round(float(df["close"].iloc[-1]), 6),
            "rsi_14d": rsi,
            "atr_14d": atr["atr_14d"],
            "atr_pct_14d": atr["atr_pct_14d"],
            "volatility": atr["volatility"],
            "indicator_method": "ccxt_exchange_ohlcv_rsi_atr_v3",
            "indicator_source": source,
            "indicator_symbol": used_symbol,
        }

        if rsi is not None and atr["atr_14d"] is not None:
            LAST_GOOD_INDICATORS[symbol] = result

        return result

    except Exception as e:
        print(f"INDICATOR ERROR {symbol}: {str(e)}")

        if symbol in LAST_GOOD_INDICATORS:
            cached = dict(LAST_GOOD_INDICATORS[symbol])
            cached["indicator_method"] = "last_good_cached_indicator"
            cached["indicator_warning"] = str(e)
            return cached

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
        url = "https://api.coingecko.com/api/v3/coins/bitcoin/market_chart"

        params = {
            "vs_currency": "usd",
            "days": "max",
            "interval": "daily",
        }

        async with httpx.AsyncClient(timeout=30) as client:
            response = await client.get(url, params=params)

            if response.status_code == 429:
                await asyncio.sleep(10)
                response = await client.get(url, params=params)

            response.raise_for_status()
            data = response.json()

        prices = data.get("prices", [])

        if len(prices) < 350:
            return {
                "status": "unknown",
                "cycle_state": "⚪ insufficient_history",
                "ma_111": None,
                "ma_350x2": None,
                "distance_pct": None,
                "top_risk": False,
                "triggered": False,
                "method": "pi_cycle_111dma_vs_350dma_x2",
                "indicator_source": "coingecko_btc_market_chart",
                "candles_used": len(prices),
            }

        df = pd.DataFrame(prices, columns=["timestamp", "close"])

        close = pd.to_numeric(df["close"], errors="coerce").dropna()

        if len(close) < 350:
            raise Exception(f"Insufficient clean BTC candles: {len(close)}")

        ma_111 = close.rolling(window=111, min_periods=111).mean().iloc[-1]
        ma_350x2 = close.rolling(window=350, min_periods=350).mean().iloc[-1] * 2

        if pd.isna(ma_111) or pd.isna(ma_350x2) or ma_111 <= 0:
            raise Exception("Pi Cycle moving averages unavailable")

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
            "indicator_source": "coingecko_btc_market_chart",
            "candles_used": len(close),
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
            "indicator_source": "coingecko_btc_market_chart",
            "error": str(e),
        }
