from fastapi import APIRouter
from app.sources import get_market_snapshot

router = APIRouter()


def calculate_score(coin):

    score = 0
    confirmations = []
    blockers = []

    rsi = coin.get("rsi_14d")
    volatility = coin.get("volatility")
    trend = coin.get("trend")
    volume = coin.get("usd_24h_vol", 0)

    if rsi:

        if rsi > 78:
            score += 30
            confirmations.append("extreme_rsi")

        elif rsi > 70:
            score += 15
            confirmations.append("high_rsi")

        elif rsi < 35:
            score -= 10
            blockers.append("oversold")

    else:
        blockers.append("rsi_missing")

    if volatility == "🔴 high":
        score += 10
        confirmations.append("high_volatility")

    elif volatility == "🟢 low":
        score -= 5

    if trend == "🟢 strengthening":
        score += 10
        confirmations.append("trend_strengthening")

    elif trend == "🟠 weakening":
        score -= 10
        blockers.append("trend_weakening")

    if volume > 100_000_000:
        score += 5
        confirmations.append("strong_volume")

    return {
        "score": score,
        "confirmations": confirmations,
        "blockers": blockers
    }


@router.get("/market/exit-engine")
async def exit_engine():

    snapshot = await get_market_snapshot()

    coins = snapshot.get("coins", {})

    signals = {}

    total_score = 0

    for ticker, coin in coins.items():

        score_data = calculate_score(coin)

        score = score_data["score"]

        total_score += score

        signal = "HOLD"

        sell_pct = 0

        if score >= 50:
            signal = "STRONG_SELL"
            sell_pct = 50

        elif score >= 30:
            signal = "PARTIAL_SELL"
            sell_pct = 25

        signals[ticker] = {
            "signal": signal,
            "score": score,
            "sell_pct": sell_pct,
            "confirmations": score_data["confirmations"],
            "blockers": score_data["blockers"],
            "price": coin.get("usd"),
            "change_24h": coin.get("usd_24h_change"),
            "volume_24h": coin.get("usd_24h_vol"),
            "rsi_14d": coin.get("rsi_14d"),
            "atr_14d": coin.get("atr_14d"),
            "volatility": coin.get("volatility"),
            "trend": coin.get("trend")
        }

    return {
        "engine_version": "1.0-phase-10-live-indicators",
        "engine_status": "active",
        "global_action": "NO_FULL_EXIT",
        "total_market_score": total_score,
        "signals": signals
    }
